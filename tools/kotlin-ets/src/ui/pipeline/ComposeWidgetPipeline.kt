@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.pipeline

import dev.ets.*
import dev.ets.compose.ComposeSourceFunctionLowering
import dev.ets.compose.ComposeInvocationContext
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.compose.ComposeWidgetRule
import dev.ets.compose.composeHostProvidedRootDefault
import dev.ets.compose.composeEmptyModifierDefault
import dev.ets.harmony.HarmonyWidgetBackend
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrProperty
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.types.classFqName
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.name.FqName

/** Production boundary from resolved Compose IR through the neutral widget model to emitted ETS. */
class ComposeWidgetPipeline(
    private val backend: EtsBackend,
    private val runtime: EtsRuntimeSupport,
    private val widgetRules: List<ComposeWidgetRule> = emptyList(),
    private val packageEntryComponent: Boolean = false,
) {
    fun compile(module: IrModuleFragment, entryFqName: String): String =
        emitEtsProgram(lower(module, entryFqName), ComposeRuntime(runtime))

    fun lower(module: IrModuleFragment, entryFqName: String): EtsProgram {
        backend.validateSource(module)
        val matches = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.fqNameWhenAvailable?.asString() == entryFqName }
        require(matches.size == 1) { "Expected one top-level widget entry $entryFqName; found ${matches.size}" }
        val entry = matches.single()
        val selected = selectSourceDeclarations(module, entryFqName,
            targetOwnsSourceArgument = { call, index ->
                backend.language.callRules.any { it.ownsSourceArgumentDependency(call, index) }
            },
            retainUnreferencedFileInitializer = ::hasSourceFileInitializerEffects,
            prune = false).declarations
        if (entry.parent !is IrFile || entry.extensionReceiverParameter != null || entry.typeParameters.isNotEmpty()) {
            backend.diagnostics.unsupported(entry, "Widget pipeline entry must be a non-generic top-level function without a receiver")
        }
        entry.valueParameters.firstOrNull { it.type.classFqName?.asString() in frameworkStateTypes }
            ?.let { parameter ->
                val type = parameter.type.classFqName?.asString()!!.substringAfterLast('.')
                backend.diagnostics.unsupported(parameter,
                    "Observed or shared $type parameters require target state ownership and are not supported")
        }

        val scope = Scope()
        val entrySemantics = FunctionTargetSemantics(
            parameterBinding = { parameter, type ->
                if (parameter.type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.Modifier" &&
                    composeEmptyModifierDefault(
                        parameter.defaultValue?.expression))
                    emptyModifierValue(backend.language.source(parameter)) else null
            },
            retainSourceDefault = { parameter ->
                !composeHostProvidedRootDefault(parameter.defaultValue?.expression)
            })
        val parameters = backend.parameters(entry, scope, entrySemantics)
        val state = ComposeStateLowering(backend.language, backend.diagnostics)
            .lower(entry, scope, entry.name.asString())
        val source = backend.language.source(entry)
        val invocationContext = ComposeInvocationContext(backend.language)
        val materialContextRequired = invocationContext.initialize(module, entry, state.scope)
        val component = if (state.fields.isEmpty() && !packageEntryComponent) null
            else componentBindings(entry, parameters, state)
        val props = component?.props.orEmpty()
        val contextField = if (component != null) invocationContext.bindComponent(entry, state.scope) else null
        val fields = listOfNotNull(contextField) + (component?.fields ?: state.fields)
        val pagers = component?.pagers ?: state.pagers
        val scrolls = component?.scrolls ?: state.scrolls
        val lazyLists = component?.lazyLists ?: state.lazyLists
        val helpers = ComposeSourceFunctionLowering(backend, backend.diagnostics,
            pagers, scrolls, lazyLists, widgetRules, materialContextRequired,
            component?.let { etsClassSymbol(entry.name.asString(), source).type as EtsNamedType })
        val entryPlan = if (component != null)
            helpers.lowerEntryPlan(entry, state.scope, state.handledStatements, entrySemantics) else null
        val model = entryPlan?.model ?: helpers.lowerEntry(entry, state.scope, state.handledStatements)
        val widgetBackend = HarmonyWidgetBackend()
        val body = widgetBackend.lower(model)
        val componentHelpers = helpers.plans().filter { it.componentMember }.map { plan ->
            plan.signature.copy(body = widgetBackend.lower(plan.model, plan.layoutScope))
        }
        val path = source.file ?: backend.diagnostics.unsupported(entry, "Widget pipeline entry requires a source file")
        val declaration: EtsDeclaration = if (component == null) {
            EtsFunction(entry.name.asString(), parameters, EtsTypes.VOID, body, source,
                exported = true, builder = true)
        } else if (entryPlan != null) {
            val method = entryPlan.signature.copy(body = body, kind = EtsFunctionKind.METHOD,
                exported = false)
            val self = EtsReference(EtsSymbol("compose-entry:${source.file}:${source.start}:this", "this",
                etsClassSymbol(entry.name.asString(), source).type, source, external = true))
            val arguments = component.props.map { field -> EtsMember(self, field.symbol.name,
                field.symbol.type, field.symbol.source, field.symbol.id) }
            val call = EtsCall(EtsMember(self, method.name, method.symbol.type, source, method.symbol.id),
                arguments, EtsTypes.VOID, source)
            val build = EtsFunction("build", emptyList(), EtsTypes.VOID,
                listOf(widgetBackend.entryContainer(call, source)), source,
                kind = EtsFunctionKind.METHOD, build = true)
            EtsClass(entry.name.asString(), props + fields + componentHelpers + method + build, source,
                exported = true, component = true, entry = props.none { it.required })
        } else {
            val build = EtsFunction("build", emptyList(), EtsTypes.VOID, body, source,
                kind = EtsFunctionKind.METHOD, build = true)
            EtsClass(entry.name.asString(), props + fields + build, source,
                exported = true, component = true, entry = props.none { it.required })
        }
        val files = linkedMapOf<String, MutableList<EtsDeclaration>>()
        module.files.forEach { file ->
            val selectedDeclarations = file.declarations.filter { it in selected }
            if (selectedDeclarations.isEmpty()) return@forEach
            backend.diagnostics.currentFile = file.fileEntry.name
            val selectedProperties = selectedDeclarations.filterIsInstance<IrProperty>().toSet()
            val declarations = selectedDeclarations.flatMap { source ->
                if (source is IrSimpleFunction && source.hasAnnotation(composable) && source.returnType.isUnit()) emptyList()
                else IrDeclarationToEts.lower(source, backend.language, backend.diagnostics)
            } + IrFileToEts.initialization(file, backend.language, selectedProperties)
            if (declarations.isNotEmpty()) {
                files.getOrPut(file.fileEntry.name) { mutableListOf() } += declarations
            }
        }
        helpers.plans().filterNot { it.componentMember }.forEach { plan ->
            files.getOrPut(plan.sourcePath) { mutableListOf() } +=
                plan.signature.copy(body = widgetBackend.lower(plan.model, plan.layoutScope))
        }
        widgetBackend.supportDeclarations().forEach { support ->
            files.getOrPut(requireNotNull(support.source.file)) { mutableListOf() } += support
        }
        files.getOrPut(path) { mutableListOf() } += declaration
        val linked = backend.link(EtsProgram(files.map { (sourcePath, declarations) ->
            EtsFile(sourcePath, declarations)
        }, imports = state.imports))
        val program = bindReactiveBuilderArguments(simplifyPureUiEvaluationBindings(linked))
        EtsValidator().validate(program)
        return program
    }

    private data class ComponentBindings(
        val props: List<EtsField>,
        val fields: List<EtsField>,
        val pagers: Map<org.jetbrains.kotlin.ir.symbols.IrValueSymbol, ComposeStateLowering.PagerStateBinding>,
        val scrolls: Map<org.jetbrains.kotlin.ir.symbols.IrValueSymbol, ComposeStateLowering.ScrollStateBinding>,
        val lazyLists: Map<org.jetbrains.kotlin.ir.symbols.IrValueSymbol, ComposeStateLowering.LazyListStateBinding>,
    )

    private fun componentBindings(entry: IrSimpleFunction, parameters: List<EtsParameter>,
        state: ComposeStateLowering.Plan): ComponentBindings {
        val at = backend.language.source(entry)
        val self = EtsReference(EtsSymbol("compose-props:${at.file}:${at.start}:this", "this",
            etsClassSymbol(entry.name.asString(), at).type, at, external = true))
        val members = parameters.associate { parameter -> parameter.symbol.id to EtsMember(self,
            parameter.symbol.name, parameter.symbol.type, parameter.symbol.source, parameter.symbol.id) }

        lateinit var rewriteStatement: (EtsStatement) -> EtsStatement
        fun expression(value: EtsExpression): EtsExpression = when (value) {
            is EtsReference -> members[value.symbol.id] ?: value
            is EtsSuper, is EtsLiteral, is EtsUndefined -> value
            is EtsMember -> value.copy(receiver = expression(value.receiver))
            is EtsCall -> value.copy(callee = expression(value.callee),
                arguments = value.arguments.map(::expression))
            is EtsNew -> value.copy(arguments = value.arguments.map(::expression))
            is EtsBinary -> value.copy(left = expression(value.left), right = expression(value.right))
            is EtsUnary -> value.copy(operand = expression(value.operand))
            is EtsConditional -> value.copy(condition = expression(value.condition),
                whenTrue = expression(value.whenTrue), whenFalse = expression(value.whenFalse))
            is EtsAssignment -> value.copy(target = expression(value.target), value = expression(value.value))
            is EtsCast -> value.copy(value = expression(value.value))
            is EtsArray -> value.copy(elements = value.elements.map(::expression))
            is EtsObject -> value.copy(fields = value.fields.mapValues { expression(it.value) })
            is EtsLambda -> value.copy(parameters = value.parameters.map { parameter ->
                parameter.copy(defaultValue = parameter.defaultValue?.let(::expression))
            }, body = value.body.map(rewriteStatement))
        }

        rewriteStatement = { value -> when (value) {
            is EtsVariable -> value.copy(initializer = value.initializer?.let(::expression))
            is EtsExpressionStatement -> value.copy(expression = expression(value.expression))
            is EtsReturn -> value.copy(value = value.value?.let(::expression))
            is EtsThrow -> value.copy(value = expression(value.value))
            is EtsTry -> value.copy(body = value.body.map(rewriteStatement),
                handler = value.handler?.let { it.copy(body = it.body.map(rewriteStatement)) },
                finallyBody = value.finallyBody?.map(rewriteStatement))
            is EtsSuperConstructorCall -> value.copy(arguments = value.arguments.map(::expression))
            is EtsBlock -> value.copy(statements = value.statements.map(rewriteStatement))
            is EtsIf -> value.copy(branches = value.branches.map { branch -> branch.copy(
                condition = branch.condition?.let(::expression), body = branch.body.map(rewriteStatement)) })
            is EtsLoop -> value.copy(condition = expression(value.condition), body = value.body.map(rewriteStatement))
            is EtsJump -> value
            is EtsUiElement -> value.copy(call = expression(value.call) as EtsCall,
                children = value.children?.map(rewriteStatement),
                attributes = value.attributes.map { expression(it) as EtsCall })
            is EtsUiComponent -> value.copy(properties = value.properties.mapValues { expression(it.value) })
            is EtsUiForEach -> value.copy(items = expression(value.items),
                body = value.body.map(rewriteStatement), key = value.key?.let(::expression) as? EtsLambda)
            is EtsUiLazyForEach -> value.copy(dataSource = expression(value.dataSource),
                body = value.body.map(rewriteStatement), key = value.key?.let(::expression) as? EtsLambda)
            is EtsFunction -> value.copy(parameters = value.parameters.map { parameter ->
                parameter.copy(defaultValue = parameter.defaultValue?.let(::expression))
            }, body = value.body.map(rewriteStatement))
        } }

        state.scope.bindings.replaceAll { _, value -> expression(value) }
        entry.valueParameters.forEach { source ->
            val binding = state.scope.bindings[source.symbol] as? EtsReference ?: return@forEach
            members[binding.symbol.id]?.let { member -> state.scope.bindings[source.symbol] = member }
        }
        val props = parameters.map { parameter -> EtsField(parameter.symbol,
            parameter.defaultValue?.let(::expression), prop = true,
            required = parameter.defaultValue == null) }
        val fields = state.fields.map { field -> field.copy(initializer = field.initializer?.let(::expression)) }
        val pagers = state.pagers.mapValues { (_, value) -> value.copy(
            currentPage = expression(value.currentPage), pageCount = expression(value.pageCount),
            controller = expression(value.controller)) }
        val scrolls = state.scrolls.mapValues { (_, value) -> value.copy(offset = expression(value.offset)) }
        val lazyLists = state.lazyLists.mapValues { (_, value) -> value.copy(
            initialIndex = expression(value.initialIndex), initialOffset = expression(value.initialOffset),
            firstVisibleIndex = expression(value.firstVisibleIndex), controller = expression(value.controller),
            initialOffsetApplied = value.initialOffsetApplied?.let(::expression)) }
        return ComponentBindings(props, fields, pagers, scrolls, lazyLists)
    }

    private companion object {
        val composable = FqName("androidx.compose.runtime.Composable")
        val frameworkStateTypes = setOf(
            "androidx.compose.foundation.lazy.LazyListState",
            "androidx.compose.foundation.pager.PagerState",
            "androidx.compose.foundation.ScrollState",
        )
    }
}
