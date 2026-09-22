package dev.ets.pipeline

import dev.ets.*
import dev.ets.compose.ComposeInputContracts
import dev.ets.compose.ComposeHelperLowering
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import org.jetbrains.kotlin.ir.declarations.IrFile
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.types.classFqName
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

/** Production boundary from resolved Compose IR through the neutral widget model to emitted ETS. */
class ComposeWidgetPipeline(
    private val backend: EtsBackend,
    private val runtime: EtsRuntimeSupport,
) {
    fun compile(module: IrModuleFragment, entryFqName: String): String {
        backend.validateSource(module)
        val matches = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.fqNameWhenAvailable?.asString() == entryFqName }
        require(matches.size == 1) { "Expected one top-level widget entry $entryFqName; found ${matches.size}" }
        val entry = matches.single()
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
        val parameters = backend.parameters(entry, scope)
        val state = ComposeStateLowering(backend.language, backend.diagnostics)
            .lower(entry, scope, entry.name.asString())
        val props = if (state.fields.isEmpty()) emptyList()
            else componentProps(entry, parameters, state.scope)
        val helpers = ComposeHelperLowering(backend, backend.diagnostics,
            state.pagers, state.scrolls, state.lazyLists)
        val model = helpers.lowerEntry(entry, state.scope, state.handledStatements)
        val widgetBackend = HarmonyWidgetBackend()
        val body = widgetBackend.lower(model)
        val source = backend.language.source(entry)
        val path = source.file ?: backend.diagnostics.unsupported(entry, "Widget pipeline entry requires a source file")
        val declaration: EtsDeclaration = if (state.fields.isEmpty()) {
            EtsFunction(entry.name.asString(), parameters, EtsTypes.VOID, body, source,
                exported = true, builder = true)
        } else {
            val build = EtsFunction("build", emptyList(), EtsTypes.VOID, body, source,
                kind = EtsFunctionKind.METHOD, build = true)
            EtsClass(entry.name.asString(), props + state.fields + build, source,
                exported = true, component = true, entry = parameters.isEmpty())
        }
        val files = linkedMapOf<String, MutableList<EtsDeclaration>>()
        ComposeInputContracts(backend.language, backend.diagnostics).lower(entry).forEach { (contractPath, contract) ->
            files.getOrPut(contractPath) { mutableListOf() } += contract
        }
        helpers.plans().forEach { plan ->
            files.getOrPut(plan.sourcePath) { mutableListOf() } +=
                plan.signature.copy(body = widgetBackend.lower(plan.model))
        }
        files.getOrPut(path) { mutableListOf() } += declaration
        val program = backend.link(EtsProgram(files.map { (sourcePath, declarations) ->
            EtsFile(sourcePath, declarations)
        }, imports = state.imports))
        EtsValidator().validate(program)
        return emitEtsProgram(program, runtime)
    }

    private fun componentProps(entry: IrSimpleFunction, parameters: List<EtsParameter>,
        scope: Scope): List<EtsField> {
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
                body = value.body.map(rewriteStatement))
            is EtsUiLazyForEach -> value.copy(dataSource = expression(value.dataSource),
                body = value.body.map(rewriteStatement), key = value.key?.let(::expression) as? EtsLambda)
            is EtsFunction -> value.copy(parameters = value.parameters.map { parameter ->
                parameter.copy(defaultValue = parameter.defaultValue?.let(::expression))
            }, body = value.body.map(rewriteStatement))
        } }

        entry.valueParameters.zip(parameters).forEach { (source, parameter) ->
            scope.bindings[source.symbol] = members.getValue(parameter.symbol.id)
        }
        return parameters.map { parameter -> EtsField(parameter.symbol,
            parameter.defaultValue?.let(::expression), prop = true,
            required = parameter.defaultValue == null) }
    }

    private companion object {
        val frameworkStateTypes = setOf(
            "androidx.compose.foundation.lazy.LazyListState",
            "androidx.compose.foundation.pager.PagerState",
            "androidx.compose.foundation.ScrollState",
        )
    }
}
