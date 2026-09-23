@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

internal data class ImplicitContextContract(val identity: String, val parameterName: String, val type: EtsType)

internal fun bindImplicitContextArguments(contracts: List<ImplicitContextContract>,
    ambientValues: Map<String, EtsExpression>, replacements: Map<String, EtsExpression>, at: SourceSpan): List<EtsExpression> {
    val unknown = replacements.keys - contracts.map { it.identity }.toSet()
    if (unknown.isNotEmpty()) throw InvalidTarget(at,
        "Unknown implicit context replacement: ${unknown.sorted().joinToString()}")
    return contracts.map { contract ->
        val value = replacements[contract.identity] ?: ambientValues[contract.identity]
            ?: throw InvalidTarget(at,
                "Missing implicit context ${contract.identity}; expected ${contract.type}")
        if (!etsAssignable(value.type, contract.type)) throw InvalidTarget(at,
            "Implicit context ${contract.identity} has target type ${value.type}; expected ${contract.type}")
        value
    }
}

/** Consumes resolved, pre-Compose-lowering IR. No source spelling is used for API dispatch. */
class ComposeLowering(val language: Language, val diagnostics: DiagnosticSink,
    private val adapters: AdapterModules = AdapterModules()) {
    private val bindingSymbols = linkedMapOf<IrValueSymbol, EtsSymbol>()
    private data class Pager(val name: String, val count: IrExpression, val scope: Scope)
    private val fields = mutableListOf<EtsField>()
    private val states = linkedMapOf<IrValueSymbol, String>()
    private val pagers = linkedMapOf<IrValueSymbol, Pager>()
    private val coroutineScopes = mutableSetOf<IrValueSymbol>()
    private val slots = mutableSetOf<IrValueSymbol>()
    private val builders = linkedSetOf<IrSimpleFunction>()
    private val builderSymbols = linkedMapOf<IrSimpleFunction, EtsSymbol>()
    private val modifierSpecializations = linkedMapOf<String, Pair<IrSimpleFunction, EtsFunction>>()
    private val activeSpecializations = mutableSetOf<IrSimpleFunction>()
    private val slotMethods = mutableListOf<EtsFunction>()
    private val constraintBuilders = mutableListOf<EtsFunction>()
    private val constraintDataClasses = mutableListOf<EtsClass>()
    private val slotMethodNames = linkedSetOf<String>()
    private val fieldNames = mutableSetOf<String>()
    private val initializedBuilderFiles = linkedMapOf<IrFile, EtsFunction>()
    private lateinit var root: IrSimpleFunction
    private lateinit var pageReceiver: EtsSymbol
    private var usesMaterialTypography = false
    private var usesMaterialContext = false
    private var usesCompositionContext = false
    private var usesFocusManager = false
    private val touchBoxes = linkedMapOf<IrCall, TouchTargets>()
    private val shapes by lazy { language.callRules.filterIsInstance<ComposeShapeRule>().single() }
    private val compositionLocals by lazy {
        language.callRules.filterIsInstance<ComposeCompositionLocalRule>().single()
    }

    private data class ContextParameter(val contract: ImplicitContextContract, val parameter: EtsParameter)

    fun lower(module: IrModuleFragment, entryName: String): EtsProgram {
        fields.clear(); states.clear(); pagers.clear(); coroutineScopes.clear()
        slots.clear(); builders.clear(); fieldNames.clear(); slotMethods.clear(); constraintBuilders.clear(); constraintDataClasses.clear(); slotMethodNames.clear()
        usesMaterialTypography = false
        touchBoxes.clear()
        bindingSymbols.clear()
        builderSymbols.clear()
        modifierSpecializations.clear(); activeSpecializations.clear()
        initializedBuilderFiles.clear()
        compositionLocals.prepareForLowering(module, language)
        usesCompositionContext = compositionLocals.contextRequired
        usesMaterialContext = requiresMaterialContext(module)
        usesFocusManager = requiresFocusManager(module)
        val declarations = module.files.flatMap { it.declarations }
        val functions = declarations.filterIsInstance<IrSimpleFunction>()
        val entries = functions.filter { it.name.asString() == entryName || symbolName(it) == entryName }
        root = entries.singleOrNull() ?: diagnostics.unsupported(module, "Expected one source entry: $entryName")
        diagnostics.currentFile = sourceFile(root)?.fileEntry?.name
        pageReceiver = EtsSymbol("ui:this", "this", etsClassSymbol(root.name.asString(), language.source(root)).type, language.source(root), external = true)
        if (!isUiBuilder(root)) diagnostics.unsupported(root, "UI entry must be @Composable and return Unit")
        val rootScope = scope()
        if (usesCompositionContext) {
            val at = language.source(root)
            rootScope.ambientValues[COMPOSITION_CONTEXT] = compositionLocals.defaultContext(language, rootScope, at)
        }
        if (usesMaterialContext) {
            val at = language.source(root)
            rootScope.ambientValues[MATERIAL_CONTEXT] = defaultMaterialContext(at, shapes.initialShapes(at))
        }
        val rootArguments = root.valueParameters.map { parameter ->
            val emitted = parameter.defaultValue?.expression?.let { language.expression(it, rootScope) } ?: run {
                val name = parameter.name.asString()
                val type = language.type(parameter.type)
                fieldNames += name
                fields += EtsField(EtsSymbol("ui:entry-prop:$name", name, type, language.source(parameter)),
                    prop = true, required = true)
                field(name, type, parameter)
            }
            rootScope.bindings[parameter.symbol] = emitted
            emitted
        }
        val rootMethod = builder(root)
        val methods = mutableListOf(rootMethod)
        val emitted = mutableSetOf(root)
        while (builders.any { it !in emitted }) {
            val next = builders.first { it !in emitted }
            emitted += next
            methods += builder(next)
        }
        methods += modifierSpecializations.values.map { it.second }
        // Explicit projections can make source value helpers unreachable. Reuse the
        // symbol worklist before lowering remaining classes, not a second UI parser.
        if (diagnostics.omittedUiElements.isNotEmpty())
            selectSourceDeclarations(module, entryName, ignored = diagnostics.omittedUiElements)
        val retained = module.files.flatMap { it.declarations }.toSet()
        val ownership = BuilderOwnership(methods + slotMethods + constraintBuilders, rootMethod.symbol.id, pageReceiver.id)
        val files = linkedMapOf<String, MutableList<EtsDeclaration>>()
        for (declaration in declarations.filter { it in retained }) {
            diagnostics.currentFile = sourceFile(declaration)?.fileEntry?.name
            val file = files.getOrPut(diagnostics.currentFile!!) { mutableListOf() }
            when (declaration) {
                is IrSimpleFunction -> if (!isUiBuilder(declaration)) {
                    file += language.function(declaration, scope()).copy(exported =
                        declaration.visibility != org.jetbrains.kotlin.descriptors.DescriptorVisibilities.PRIVATE)
                } else {
                    val symbol = builderSymbols[declaration]
                    if (symbol?.id in ownership.globalIds) {
                        file += ownership.rewrite(methods.single { it.symbol.id == symbol!!.id }).copy(
                            kind = EtsFunctionKind.FUNCTION,
                            exported = declaration.visibility != org.jetbrains.kotlin.descriptors.DescriptorVisibilities.PRIVATE)
                    }
                }
                is IrClass -> file += language.clazz(declaration).copy(exported =
                    declaration.visibility != org.jetbrains.kotlin.descriptors.DescriptorVisibilities.PRIVATE)
                is IrProperty -> file += lowerTopLevelProperty(declaration, language)
                else -> diagnostics.unsupported(declaration, "Unsupported top-level UI module declaration")
            }
        }
        for (source in declarations.filter { it in retained }.mapNotNull(::sourceFile).distinct()) {
            diagnostics.currentFile = source.fileEntry.name
            files.getOrPut(source.fileEntry.name) { mutableListOf() } += lowerFileInitialization(source, language)
            initializedBuilderFiles[source]?.let { files.getValue(source.fileEntry.name).add(it) }
        }
        modifierSpecializations.values.forEach { (source, method) ->
            if (method.symbol.id in ownership.globalIds) files.getOrPut(sourceFile(source)!!.fileEntry.name) { mutableListOf() }
                .add(ownership.rewrite(method).copy(kind = EtsFunctionKind.FUNCTION,
                    exported = source.visibility != org.jetbrains.kotlin.descriptors.DescriptorVisibilities.PRIVATE))
        }
        constraintBuilders.forEach { method ->
            if (method.symbol.id !in ownership.globalIds) throw Unsupported(Diagnostic("UNSUPPORTED",
                "BoxWithConstraints content must pass state through explicit parameters", method.source))
            files.getOrPut(method.source.file!!) { mutableListOf() }
                .add(ownership.rewrite(method).copy(kind = EtsFunctionKind.FUNCTION))
        }
        slotMethods.filter { it.symbol.id in ownership.globalIds }.forEach { method ->
            files.getOrPut(method.source.file!!) { mutableListOf() }
                .add(ownership.rewrite(method).copy(kind = EtsFunctionKind.FUNCTION))
        }
        constraintDataClasses.forEach { declaration ->
            files.getOrPut(declaration.source.file!!) { mutableListOf() }.add(declaration)
        }
        diagnostics.currentFile = sourceFile(root)?.fileEntry?.name
        val name = root.name.asString()
        val entryBody = native("Stack", listOf(stackOptions(root)), root,
            listOf(EtsUiElement(methodCall(builderSymbol(root), contextArguments(rootScope, root) + rootArguments, root)))).copy(attributes = listOf(
                attribute("width", listOf(literal("100%", root)), root),
                attribute("height", listOf(literal("100%", root)), root)))
        val build = EtsFunction("build", emptyList(), EtsTypes.VOID, listOf(entryBody), language.source(root),
            kind = EtsFunctionKind.METHOD, build = true)
        val lifecycle = if (usesFocusManager) listOf(focusContextInit(root, language)) else emptyList()
        val pageMethods = (methods + slotMethods).filter { it.symbol.id !in ownership.globalIds }.map(ownership::rewrite)
        if (fields.isNotEmpty()) initializedBuilderFiles[root.parent as? IrFile]?.let { guard ->
            val at = language.source(root)
            val name = fieldName("__etsFileReady", root)
            fields.add(0, EtsField(EtsSymbol("ui:file-ready", name, EtsTypes.BOOLEAN, at),
                EtsCall(EtsReference(guard.symbol), emptyList(), EtsTypes.BOOLEAN, at), visibility = EtsVisibility.PRIVATE))
        }
        val hasRequiredInputs = fields.filterIsInstance<EtsField>().any { it.prop && it.required }
        val component = EtsClass(name, fields + lifecycle + pageMethods + build, language.source(root), exported = true,
            component = true, entry = !hasRequiredInputs)
        files.getOrPut(language.source(root).file!!) { mutableListOf() }.add(component)
        return bindReactiveBuilderArguments(linkAdapterDeclarations(EtsProgram(files.filterValues { it.isNotEmpty() }.map { (path, declarations) -> EtsFile(path, declarations) },
            if (usesMaterialTypography) listOf(EtsImport("@ohos.graphics.drawing", "__etsDrawing", default = true)) else emptyList()), language.callRules))
    }

    private val target = ArkUiCalls(language, diagnostics)
    private val uiRules: List<CallRule> by lazy {
        adapters.rules(object : AdapterUiServices {
            override fun content(expression: IrExpression, scope: Scope) = uiLambdaBody(expression, scope)
            override fun decorate(modifier: IrExpression?, scope: Scope, element: EtsUiElement, boundaries: Set<String>) =
                modifiers(modifier, scope, ComposeElement(element, boundaries))
        }) + listOf(
            object : CallRule {
                override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
                override fun lowerUi(call: IrCall, language: Language, scope: Scope) = sourceUiCall(call, scope)
            },
            object : CallRule {
                override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
                override fun lowerUi(call: IrCall, language: Language, scope: Scope) =
                    if (symbolName(call.symbol.owner) == "kotlin.repeat") repeatUi(call, scope) else null
            },
            ComposeColumnRule(target, { value, scope -> uiLambdaBodyWithAxis(value, scope, "height") }, ::modifiers),
            ComposeForEachRule(target, { binding(it) }, { body, scope -> uiBody(body, scope) }),
            ComposeRowRule(target, { value, scope -> uiLambdaBodyWithAxis(value, scope, "width") }, touchBoxes, ::modifiers),
            ComposeBoxRule(target, ::uiLambdaBody, touchBoxes, ::modifiers),
            ComposeBoxWithConstraintsRule(target, ::constraintsContent, ::modifiers),
            ComposeCompositionLocalProviderRule(compositionLocals, diagnostics, ::provideCompositionContext),
            ComposeMaterialThemeRule(target, ::provideMaterialContext),
            ComposeProvideTextStyleRule(target, ::provideMaterialContext),
            ComposeSurfaceRule(target, ::surfaceContent, { content, scope -> surfaceContent(content, scope, "height") },
                ::modifierBounds, ::modifiers),
            ComposeSpacerRule(target, ::modifiers),
            ComposeTextRule(target, ::dimension,
                { usesMaterialTypography = true }, ::modifiers),
            ComposeButtonRule(target, ::uiLambdaBody, ::callback, ::modifiers),
            ComposeBasicTextRule(target, ::modifiers),
            ComposeBasicTextFieldRule(target, ::bindInnerTextField, { fn, scope ->
                uiBody(fn.body ?: diagnostics.unsupported(fn, "Missing decoration body"), scope) }, ::modifiers),
            ComposeTextFieldDecorationRule(target, ::uiLambdaBody, ::modifiers),
            ComposeClickableTextRule(target, ::modifiers),
            ComposeHorizontalDividerRule(target, ::colorValue, ::dimension, ::modifiers),
            ComposeVerticalDividerRule(target, ::colorValue, ::dimension, ::modifiers),
            ComposeCheckboxRule(target, ::modifiers),
            ComposeSwitchRule(target, ::modifiers),
            ComposeImageRule(target, ::modifiers),
            ComposeIconRule(target, ::colorValue, ::modifiers),
            ComposeAsyncImageRule(target, ::modifiers),
            ComposeHorizontalPagerRule(target, ::pagerBinding, { binding(it) }, { body, scope -> uiBody(body, scope) },
                ::indexItems, ::modifiers),
            ComposeLazyColumnRule(target, { binding(it) }, { body, scope -> uiBody(body, scope) }, ::modifiers),
            ComposeLazyVerticalGridRule(target, { binding(it) }, { body, scope -> uiBody(body, scope) },
                { value, scope -> dimension(value, scope, "dp") }, ::modifiers),
        )
    }

    private fun scope() = Scope(callRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope) = platformCall(call, scope)
        override fun lowerStatement(call: IrCall, language: Language, scope: Scope) = platformStatement(call, scope)
    }, callRules = uiRules)

    private fun expression(value: IrExpression, scope: Scope) = language.expression(value, scope)
    private fun literal(value: Any, owner: IrElement) = target.literal(value, owner)
    private fun call(name: String, args: List<EtsExpression>, owner: IrElement,
        types: List<EtsType> = args.map { it.type }, result: EtsType = EtsTypes.VOID,
        receiver: EtsExpression? = null, identity: String = "arkui:$name"): EtsCall =
        target.call(name, args, owner, types, result, receiver, identity)

    private fun contextContracts(): List<ImplicitContextContract> = buildList {
        if (usesCompositionContext) add(ImplicitContextContract(COMPOSITION_CONTEXT,
            "__etsCompositionContext", compositionContextType))
        if (usesMaterialContext) add(ImplicitContextContract(MATERIAL_CONTEXT,
            "__etsMaterialContext", materialContextType))
    }

    private fun contextTypes(): List<EtsType> = contextContracts().map { it.type }

    private fun builderSymbol(function: IrSimpleFunction): EtsSymbol = builderSymbols.getOrPut(function) {
        val source = SourceSpan(sourceFile(function)?.fileEntry?.name, function.startOffset, function.endOffset)
        etsFunctionSymbol(function.name.asString(), contextTypes() + function.valueParameters.map {
            if (it.type.hasAnnotation(COMPOSABLE)) slotType(it.type) else language.type(it.type)
        }, EtsTypes.VOID, source)
    }
    private fun methodCall(symbol: EtsSymbol, args: List<EtsExpression>, owner: IrElement): EtsCall {
        val source = language.source(owner)
        return EtsCall(EtsMember(EtsReference(pageReceiver, source), symbol.name, symbol.type, source, symbol.id),
            args, EtsTypes.VOID, source)
    }
    private fun attribute(name: String, args: List<EtsExpression>, owner: IrElement) = target.attribute(name, args, owner)
    private fun native(name: String, args: List<EtsExpression>, owner: IrElement, children: List<EtsStatement>? = null) =
        target.native(name, args, owner, children)
    private fun enumValue(type: String, name: String, owner: IrElement) = target.enumValue(type, name, owner)
    private fun record(name: String, values: Map<String, EtsExpression>, owner: IrElement) = target.record(name, values, owner)
    private fun stackOptions(owner: IrElement) = target.stackOptions(owner)

    private fun binding(value: IrValueDeclaration, name: String = value.name.asString(),
        targetType: EtsType = language.type(value.type)): EtsReference =
        EtsReference(bindingSymbols.getOrPut(value.symbol) {
            EtsSymbol("ui:${bindingSymbols.size}", name, targetType, language.source(value))
        })

    private fun field(name: String, type: EtsType, element: IrElement): EtsMember {
        val source = language.source(element)
        val receiver = EtsReference(pageReceiver, source)
        return EtsMember(receiver, name, type, source)
    }

    private fun bindingWrappedBuilder() = EtsNamedType("WrappedBuilder", listOf(EtsTupleType(contextTypes())))

    private fun slotType(type: IrType): EtsType {
        val wrapped = bindingWrappedBuilder()
        return if (type is IrSimpleType && type.nullability == SimpleTypeNullability.MARKED_NULLABLE)
            EtsNullableType(wrapped) else wrapped
    }

    private fun contextArguments(scope: Scope, owner: IrElement,
        replacements: Map<String, EtsExpression> = emptyMap()): List<EtsExpression> {
        val at = language.source(owner)
        return bindImplicitContextArguments(contextContracts(), scope.ambientValues, replacements, at)
    }

    private fun boundContextParameters(scope: Scope, owner: IrElement): List<ContextParameter> {
        val at = language.source(owner)
        return contextContracts().map { contract ->
            val symbol = EtsSymbol("ui:${contract.identity}:${at.file}:${at.start}", contract.parameterName,
                contract.type, at)
            scope.ambientValues[contract.identity] = EtsReference(symbol)
            ContextParameter(contract, EtsParameter(symbol))
        }
    }

    private fun contextParameters(scope: Scope, owner: IrElement): List<EtsParameter> =
        boundContextParameters(scope, owner).map { it.parameter }

    private fun isUiBuilder(function: IrSimpleFunction): Boolean =
        function.hasAnnotation(COMPOSABLE) && function.returnType.isUnit()

    private fun builder(function: IrSimpleFunction, modifiers: Map<IrValueSymbol, IrExpression> = emptyMap(),
        aliases: Map<IrValueSymbol, IrExpression> = emptyMap(), name: String = function.name.asString(),
        ambient: Map<String, EtsExpression> = emptyMap(),
        modifierBindings: Map<IrValueSymbol, EtsExpression> = emptyMap()): EtsFunction {
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        if (modifiers.isEmpty()) builderSymbol(function)
        if (function.extensionReceiverParameter != null || function.dispatchReceiverParameter != null)
            diagnostics.unsupported(function, "Source builder receivers are not supported")
        val scope = scope()
        scope.aliases.putAll(aliases)
        scope.aliases.putAll(modifiers)
        scope.bindings.putAll(modifierBindings)
        scope.ambientValues.putAll(ambient)
        val parameters = contextParameters(scope, function) + function.valueParameters.filter { it.symbol !in modifiers }.map { parameter ->
            if (parameter.type.hasAnnotation(COMPOSABLE)) {
                if (!isContentSlotType(parameter.type))
                    diagnostics.unsupported(parameter, "Content slots currently require () -> Unit")
                slots += parameter.symbol
                val reference = binding(parameter, targetType = slotType(parameter.type))
                scope.bindings[parameter.symbol] = reference
                val default = parameter.defaultValue?.expression?.takeIf { it is IrConst && it.kind == IrConstKind.Null }
                    ?.let { EtsLiteral(null, EtsTypes.NULL, language.source(it)) }
                EtsParameter(reference.symbol, default)
            } else {
                val reference = binding(parameter)
                scope.bindings[parameter.symbol] = reference
                EtsParameter(reference.symbol, parameter.defaultValue?.expression?.let { expression(it, scope) })
            }
        }
        val body = function.body ?: diagnostics.unsupported(function, "Builder has no source body")
        val content = uiBody(body, scope, rootBody = true)
        val file = function.parent as? IrFile
        val lines = if (file != null && requiresFileInitialization(file)) {
            val guard = initializedBuilderFiles.getOrPut(file) {
                val initialization = fileInitializationCall(file)
                val at = initialization.source
                val name = ((initialization.expression as EtsCall).callee as EtsReference).symbol.name + "_ui"
                // ArkUI builders accept conditions, not standalone effect statements.
                EtsFunction(name, emptyList(), EtsTypes.BOOLEAN, listOf(initialization,
                    EtsReturn(EtsLiteral(true, EtsTypes.BOOLEAN, at), at)), at, exported = true)
            }
            val ready = EtsCall(EtsReference(guard.symbol), emptyList(), EtsTypes.BOOLEAN, language.source(function))
            listOf(EtsIf(listOf(EtsBranch(ready, content)), language.source(function)))
        } else content
        return EtsFunction(name, parameters, EtsTypes.VOID, lines, language.source(function),
            kind = EtsFunctionKind.METHOD, builder = true)
    }

    private fun uiBody(body: IrBody, scope: Scope, rootBody: Boolean = false): List<EtsStatement> = when (body) {
        is IrBlockBody -> uiStatements(body.statements, scope, rootBody)
        is IrExpressionBody -> uiStatement(body.expression, scope, rootBody)
        else -> diagnostics.unsupported(body, "Unsupported builder body")
    }

    private fun uiStatements(statements: List<IrStatement>, scope: Scope, rootBody: Boolean): List<EtsStatement> {
        val lines = mutableListOf<EtsStatement>()
        statements.forEachIndexed { index, statement ->
            if (statement !is IrVariable) {
                lines += uiStatement(statement, scope, rootBody)
            } else {
                if (statement.isVar) diagnostics.unsupported(statement, "Mutable builder local requires remembered state")
                val initial = statement.initializer ?: diagnostics.unsupported(statement, "Uninitialized builder variable")
                if (remember(statement, initial, scope, rootBody)) return@forEachIndexed
                if (isConstraintDimensionRead(initial, scope)) {
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                if (statement.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE &&
                    uses(statement, statements.drop(index + 1)) == 1 && stableRead(initial, scope)) {
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                val platformValue = initial.type.classOrNull?.owner?.fqNameWhenAvailable?.asString() == "androidx.compose.ui.Modifier"
                if (initial is IrCall && symbolName(initial.symbol.owner) == "androidx.compose.foundation.rememberScrollState") {
                    ScrollModifier(target, language).validateState(initial, scope)
                    if (uses(statement, statements.drop(index + 1), includeOmitted = true) > 1)
                        diagnostics.unsupported(statement, "Shared or observed ScrollState requires explicit target state binding")
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                if (initial is IrCall && symbolName(initial.symbol.owner) == "androidx.compose.foundation.lazy.rememberLazyListState") {
                    validateRememberLazyListState(initial, language, scope, diagnostics)
                    if (uses(statement, statements.drop(index + 1), includeOmitted = true) > 1)
                        diagnostics.unsupported(statement, "Shared or observed LazyListState requires explicit target state binding")
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                if (initial is IrFunctionExpression ||
                    (platformValue && (statement.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE || stableModifier(initial, scope)))) {
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                // Keep constant folding, but a compiler temporary's unsupported value
                // is only fatal if a consumer survives the explicit UI omissions.
                val deferred = diagnostics.reportUiDegradation &&
                    (statement.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE || platformValue) && initial !is IrConst
                var deferredFailure: Unsupported? = null
                val value = try { language.expression(initial, scope) } catch (failure: Unsupported) {
                    if (!deferred) throw failure
                    deferredFailure = failure
                    null
                }
                if (statement.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE && value is EtsLiteral) {
                    scope.aliases[statement.symbol] = initial
                    return@forEachIndexed
                }
                // Distinct compiler temporaries can inherit the same enclosing source span.
                val name = if (statement.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE)
                    "uiTemporary${statement.startOffset}_${bindingSymbols.size}" else statement.name.asString()
                val child = scope.fork()
                try {
                    child.bindings[statement.symbol] = binding(statement, name)
                    child.aliases.remove(statement.symbol)
                } catch (failure: Unsupported) {
                    if (!deferred) throw failure
                    deferredFailure = deferredFailure ?: failure
                    // Preserve source IR until a consumer needs it, never invent an ETS type.
                    child.aliases[statement.symbol] = initial
                }
                val remaining = statements.drop(index + 1)
                child.bindings.keys.toList().forEach { symbol ->
                    child.bindings[symbol] = EtsReference(capturedParameter(symbol, child).symbol)
                }
                val context = contextParameters(child, statement)
                val body = uiStatements(remaining, child, rootBody)
                if (deferred && uses(statement, remaining, includeOmitted = true) > 0 && uses(statement, remaining) == 0) {
                    if (platformValue && statement.origin != IrDeclarationOrigin.IR_TEMPORARY_VARIABLE)
                        diagnostics.omitUi(statement, "Private Modifier belongs only to explicitly omitted UI",
                            "androidx.compose.ui.Modifier", "omitted_private_modifier",
                            "Modifier construction and its argument evaluation are omitted because no retained UI consumes it.")
                    else diagnostics.omittedUiElements += statement
                    return lines + body
                }
                deferredFailure?.let { throw it }
                val captures = capturedValues(remaining, child).filter { it != statement.symbol }
                val methodName = slotMethodName("${name}_${statement.startOffset}")
                val parameters = context + listOf(capturedParameter(statement.symbol, child)) + captures.map { capturedParameter(it, child) }
                // A builder parameter evaluates a source val once; textual aliasing would duplicate calls.
                val bridge = EtsFunction(methodName, parameters, EtsTypes.VOID, body, language.source(statement), kind = EtsFunctionKind.METHOD, builder = true)
                slotMethods += bridge
                lines += EtsUiElement(methodCall(bridge.symbol, contextArguments(scope, statement) + listOf(requireNotNull(value)) + captures.map { scope.bindings.getValue(it) }, statement))
                return lines
            }
        }
        return lines
    }

    private fun uses(variable: IrVariable, elements: List<IrElement>, includeOmitted: Boolean = false): Int {
        var count = 0
        val visitor = object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (includeOmitted || element !in diagnostics.omittedUiElements) element.acceptChildrenVoid(this)
            }
            override fun visitGetValue(expression: IrGetValue) {
                if (expression.symbol == variable.symbol && (includeOmitted || expression !in diagnostics.omittedUiElements)) count++
            }
        }
        elements.forEach { it.acceptVoid(visitor) }
        return count
    }

    // A mutable read can change while later named arguments run. Only immutable,
    // default-accessor reads may move to their single use without a value bridge.
    private fun stableRead(expression: IrExpression, scope: Scope): Boolean = when (expression) {
        is IrConst -> true
        is IrGetValue -> scope.aliases[expression.symbol]?.let { stableRead(it, scope) }
            ?: when (val owner = expression.symbol.owner) {
                is IrVariable -> !owner.isVar && expression.symbol in scope.bindings
                is IrValueParameter -> expression.symbol in scope.bindings
                else -> false
            }
        is IrCall -> {
            val getter = expression.symbol.owner
            val api = symbolName(getter)
            if (api in setOf("kotlin.Int.unaryMinus", "kotlin.Int.unaryPlus",
                    "kotlin.Float.unaryMinus", "kotlin.Float.unaryPlus",
                    "kotlin.Double.unaryMinus", "kotlin.Double.unaryPlus") &&
                getter.valueParameters.isEmpty())
                expression.dispatchReceiver?.let { stableRead(it, scope) } == true
            else {
                val property = getter.correspondingPropertySymbol?.owner
                property != null && !property.isVar && property.getter?.symbol == getter.symbol &&
                    getter.origin == IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR &&
                    property.backingField?.isFinal == true && sourceFile(property) != null &&
                    getter.valueParameters.isEmpty() && expression.extensionReceiver == null &&
                    expression.dispatchReceiver?.let { stableRead(it, scope) } == true
            }
        }
        else -> false
    }

    private fun uiStatement(node: IrStatement, scope: Scope, rootBody: Boolean = false): List<EtsStatement> = when (node) {
        is IrVariable -> uiStatements(listOf(node), scope, rootBody)
        is IrCall -> (adaptCall(node, language, scope, CallContext.UI) as? CallResult.Ui)?.statements ?: run {
            val api = symbolName(node.symbol.owner)
            if (sourceFile(node.symbol.owner) != null || !node.type.isUnit())
                diagnostics.unsupported(node, "Unsupported resolved UI API: $api")
            diagnostics.omitUi(node, "Unsupported resolved UI API: $api", api,
                "omitted_ui_call", "Call, arguments, callbacks and any nested UI are omitted; supported siblings remain.")
            emptyList()
        }
        is IrReturn -> uiStatement(node.value, scope, rootBody)
        is IrTypeOperatorCall -> when (node.operator) {
            IrTypeOperator.IMPLICIT_COERCION_TO_UNIT,
            IrTypeOperator.IMPLICIT_CAST,
            IrTypeOperator.IMPLICIT_NOTNULL -> uiStatement(node.argument, scope, rootBody)
            else -> diagnostics.unsupported(node, "Unsupported UI type operator ${node.operator}")
        }
        is IrBlock -> uiStatements(node.statements, scope.fork(), rootBody)
        is IrComposite -> uiStatements(node.statements, scope, rootBody)
        is IrGetObjectValue -> if (node.type.isUnit()) emptyList() else diagnostics.unsupported(node, "Unexpected UI value")
        is IrConst -> if (node.kind == IrConstKind.Null || node.type.isUnit()) emptyList()
            else diagnostics.unsupported(node, "Unexpected UI constant")
        is IrGetValue -> {
            val resolved = dereference(node, scope)
            if (resolved != null && resolved !== node) uiStatement(resolved, scope, rootBody)
            else diagnostics.unsupported(node, "Unexpected UI value")
        }
        is IrWhen -> listOf(EtsIf(node.branches.filterNot { branch ->
            branch is IrElseBranch && syntheticNoWhenBranch(branch.result)
        }.map { branch -> EtsBranch(if (branch is IrElseBranch) null else expression(branch.condition, scope),
            uiStatement(branch.result, scope.fork())) }, language.source(node)))
        else -> diagnostics.unsupported(node, "Unsupported UI statement ${node::class.simpleName}")
    }

    private fun syntheticNoWhenBranch(value: IrExpression): Boolean = when (value) {
        is IrCall -> symbolName(value.symbol.owner) == "kotlin.internal.ir.noWhenBranchMatchedException"
        is IrTypeOperatorCall -> syntheticNoWhenBranch(value.argument)
        is IrBlock -> (value.statements.lastOrNull() as? IrExpression)?.let(::syntheticNoWhenBranch) == true
        is IrComposite -> (value.statements.lastOrNull() as? IrExpression)?.let(::syntheticNoWhenBranch) == true
        else -> false
    }

    private fun remember(variable: IrVariable, expression: IrExpression, scope: Scope, rootBody: Boolean): Boolean {
        val call = expression as? IrCall ?: return false
        val api = symbolName(call.symbol.owner)
        if (api !in setOf("androidx.compose.runtime.remember", "androidx.compose.runtime.saveable.rememberSaveable",
                "androidx.compose.runtime.rememberCoroutineScope",
                "androidx.compose.foundation.pager.rememberPagerState")) return false
        if (!rootBody) diagnostics.unsupported(call, "Remember is supported only in a builder's unconditional body")
        val name = variable.name.asString()
        when (api) {
            "androidx.compose.runtime.remember", "androidx.compose.runtime.saveable.rememberSaveable" -> {
                val calculation = argument(call, "calculation") ?: argument(call, "init")
                    ?: diagnostics.unsupported(call, "Remember requires a calculation")
                if (api == "androidx.compose.runtime.saveable.rememberSaveable")
                    checkArguments(call, setOf("inputs", "key", "stateSaver", "init", "calculation"))
                else checkArguments(call, setOf("calculation"))
                val result = singleResult(calculation, scope, call)
                val factory = result as? IrCall ?: diagnostics.unsupported(result, "Remember requires mutableStateOf")
                if (symbolName(factory.symbol.owner) != "androidx.compose.runtime.mutableStateOf")
                    diagnostics.unsupported(factory, "Remember supports only explicit mutableStateOf in this slice")
                checkArguments(factory, setOf("value"))
                val initial = argument(factory, "value") ?: diagnostics.unsupported(factory, "Missing state value")
                val field = fieldName(name, variable)
                fields += EtsField(EtsSymbol("ui:field:$field", field, language.type(initial.type), language.source(variable)),
                    expression(initial, scope()), visibility = EtsVisibility.PRIVATE, state = true)
                states[variable.symbol] = field
            }
            "androidx.compose.foundation.pager.rememberPagerState" -> {
                checkArguments(call, setOf("initialPage", "pageCount"))
                val count = singleResult(argument(call, "pageCount"), scope, call)
                val countValue = (count as? IrConst)?.value as? Int
                if (countValue == null || countValue <= 0)
                    diagnostics.unsupported(count, "Pager pageCount currently requires a positive integer literal")
                val initial = argument(call, "initialPage")?.let { language.expression(it, scope()) }
                    ?: EtsLiteral(0, EtsTypes.NUMBER, language.source(call))
                val field = fieldName(name + "_currentPage", variable)
                fieldName(name + "_controller", variable)
                fields += EtsField(EtsSymbol("ui:field:$field", field, EtsTypes.NUMBER, language.source(variable)), initial, visibility = EtsVisibility.PRIVATE, state = true)
                val controllerType = EtsNamedType("SwiperController")
                fields += EtsField(EtsSymbol("ui:field:${name}_controller", "${name}_controller", controllerType, language.source(variable)),
                    EtsNew(controllerType, emptyList(), language.source(variable)), visibility = EtsVisibility.PRIVATE)
                pagers[variable.symbol] = Pager(name, count, scope.fork())
            }
            else -> {
                checkArguments(call, emptySet())
                coroutineScopes += variable.symbol
            }
        }
        return true
    }

    private fun fieldName(name: String, node: IrElement): String {
        var candidate = name
        var index = 2
        while (!fieldNames.add(candidate)) candidate = "${name}_${index++}"
        return candidate
    }

    private fun singleResult(expression: IrExpression?, scope: Scope, owner: IrElement): IrExpression {
        val fn = lambda(expression, scope) ?: diagnostics.unsupported(owner, "Expected source lambda")
        val statements = (fn.body as? IrBlockBody)?.statements
            ?: diagnostics.unsupported(fn, "Expected lambda block")
        val result = statements.singleOrNull() ?: diagnostics.unsupported(fn, "Expected a single initializer expression")
        return (result as? IrReturn)?.value ?: result as? IrExpression
            ?: diagnostics.unsupported(result, "Expected initializer value")
    }

    private fun sourceUiCall(call: IrCall, scope: Scope): List<EtsStatement>? {
        val function = call.symbol.owner
        val slot = slotReceiver(call.dispatchReceiver, scope) ?: slotReceiver(call.extensionReceiver, scope)
        if (function.name.asString() == "invoke" && slot != null) {
            val extras = listOfNotNull(call.dispatchReceiver, call.extensionReceiver)
                .filter { slotReceiver(it, scope) == null } +
                (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument)
            extras.forEach { value ->
                if (!isLayoutScopeReceiver(value) && !isLayoutScopeType(value.type))
                    diagnostics.unsupported(value, "Content slot invoke currently requires a layout-scope identity")
            }
            return listOf(EtsUiElement(call("builder", contextArguments(scope, call), call, receiver = expression(slot, scope))))
        }
        if (isUiBuilder(function) && sourceFile(function) != null && !function.isExternal) {
            specializeModifierCall(call, scope)?.let { return it }
            builders += function
            return listOf(EtsUiElement(methodCall(builderSymbol(function),
                contextArguments(scope, call) + builderArguments(function, call, scope), call)))
        }
        return null
    }

    private fun specializeModifierCall(call: IrCall, scope: Scope): List<EtsStatement>? {
        val function = call.symbol.owner
        val inputs = function.valueParameters.mapIndexedNotNull { index, parameter ->
            if (parameter.type.classOrNull?.owner?.let(::symbolName) != "androidx.compose.ui.Modifier") null
            else parameter to (call.getValueArgument(index) ?: parameter.defaultValue?.expression
                ?: diagnostics.unsupported(call, "Missing Modifier argument ${parameter.name}"))
        }
        if (inputs.none { (_, value) ->
            val resolved = dereference(value, scope) as? IrCall
            resolved != null && sourceFile(resolved.symbol.owner) == null
        }) return null
        fun key(value: IrExpression): String {
            val resolved = dereference(value, scope) ?: diagnostics.unsupported(value, "Missing Modifier value")
            if (resolved is IrGetObjectValue && symbolName(resolved.symbol.owner) == "androidx.compose.ui.Modifier.Companion") return "identity"
            if (resolved is IrConst) return "${resolved.kind}:${resolved.value}"
            if (resolved is IrCall && resolved.type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.Modifier") {
                val owner = resolved.symbol.owner
                if (sourceFile(owner) != null) diagnostics.unsupported(resolved, "Source Modifier factories require a first-class target layout program")
                val signature = owner.valueParameters.joinToString(",") { "${it.name}:${it.type.render()}" }
                val receivers = listOf(resolved.extensionReceiver, resolved.dispatchReceiver)
                    .joinToString(",") { it?.let(::key) ?: "<absent>" }
                val arguments = (0 until resolved.valueArgumentsCount).joinToString(",") { index ->
                    "$index=" + (resolved.getValueArgument(index)?.let(::key) ?: "<default>")
                }
                return "${symbolName(owner)}[$signature]($receivers;$arguments)"
            }
            if (isLayoutScopeReceiver(resolved)) return "layoutScope:${resolved.type.classFqName ?: resolved.type.render()}"
            if (resolved is IrGetValue && scope.bindings[resolved.symbol]?.type == emptyModifierType) return "identity"
            if (resolved is IrGetValue) diagnostics.unsupported(resolved, "Dynamic Modifier operands require a first-class target layout program")
            val literal = language.expression(resolved, scope) as? EtsLiteral
                ?: diagnostics.unsupported(resolved, "Effectful Modifier operands require an evaluation-preserving layout program")
            return "${literal.type}:${literal.value}"
        }
        val identity = "${sourceFile(function)?.fileEntry?.name}:${function.startOffset}:${symbolName(function)}:" +
            inputs.joinToString(";") { "${it.first.index}=${key(it.second)}" }
        val method = modifierSpecializations[identity]?.second ?: run {
            if (!activeSpecializations.add(function)) diagnostics.unsupported(call, "Recursive Modifier specialization is unsupported")
            val ordinal = modifierSpecializations.values.count { it.first == function }
            val name = function.name.asString() + "_Modifier${ordinal + 1}"
            val previousFile = diagnostics.currentFile
            try {
                builder(function, inputs.associate { it.first.symbol to it.second }, scope.aliases, name,
                    scope.ambientValues, scope.bindings.filterValues { it.type == emptyModifierType }
                        .mapValues { emptyModifierValue(language.source(call)) }).also {
                    modifierSpecializations[identity] = function to it
                }
            } finally {
                activeSpecializations.remove(function)
                diagnostics.currentFile = previousFile
            }
        }
        val specialized = inputs.map { it.first }.toSet()
        val args = builderArguments(function, call, scope, skip = specialized)
        return listOf(EtsUiElement(methodCall(method.symbol, contextArguments(scope, call) + args, call)))
    }

    private fun builderArguments(function: IrSimpleFunction, call: IrCall, scope: Scope,
        skip: Set<IrValueParameter> = emptySet()): List<EtsExpression> {
        val child = scope.fork()
        return function.valueParameters.mapIndexedNotNull { index, parameter ->
            // Specialized Modifier arguments are inlined into the generated builder.
            // Evaluating them here would treat layout APIs as language values.
            if (parameter in skip) return@mapIndexedNotNull null
            val value = call.getValueArgument(index) ?: parameter.defaultValue?.expression
                ?: diagnostics.unsupported(call, "Missing builder argument ${parameter.name}")
            val previousFile = diagnostics.currentFile
            if (call.getValueArgument(index) == null) diagnostics.currentFile = sourceFile(parameter)?.fileEntry?.name
            try {
                val emitted = builderArgument(parameter, value, child, "${function.name}_${parameter.name}")
                child.bindings[parameter.symbol] = emitted
                emitted
            } finally { diagnostics.currentFile = previousFile }
        }
    }

    private fun builderArgument(parameter: IrValueParameter, value: IrExpression, scope: Scope, name: String): EtsExpression {
        if (parameter.type.hasAnnotation(COMPOSABLE)) {
            val resolved = resolveExpression(value, scope) ?: value
            if (resolved is IrConst && resolved.kind == IrConstKind.Null)
                return EtsLiteral(null, EtsTypes.NULL, language.source(value))
            return uiLambda(value, scope, name)
        }
        val fn = lambda(value, scope)
        if (fn != null && !fn.isSuspend && fn.valueParameters.isEmpty() && fn.returnType.isUnit())
            return callback(value, scope)
        return expression(value, scope)
    }

    private fun repeatUi(call: IrCall, scope: Scope): List<EtsStatement> {
        checkArguments(call, setOf("times", "action"))
        val times = argument(call, "times") ?: diagnostics.unsupported(call, "repeat requires times")
        val fn = lambda(argument(call, "action"), scope) ?: diagnostics.unsupported(call, "repeat requires action")
        val parameter = fn.valueParameters.singleOrNull() ?: diagnostics.unsupported(fn, "repeat action requires index")
        val child = scope.fork()
        child.bindings[parameter.symbol] = binding(parameter)
        return listOf(EtsUiForEach(indexItems(expression(times, scope), call),
            EtsParameter(binding(parameter).symbol), uiBody(fn.body!!, child), language.source(call)))
    }

    private fun pagerBinding(call: IrCall, scope: Scope): ComposePagerBinding {
        val state = pagerFor(argument(call, "state"), scope, call)
        return ComposePagerBinding(expression(state.count, state.scope),
            field("${state.name}_currentPage", EtsTypes.NUMBER, call),
            field("${state.name}_controller", EtsNamedType("SwiperController"), call))
    }

    private fun indexItems(count: EtsExpression, owner: IrElement): EtsExpression {
        val source = language.source(owner)
        val index = EtsSymbol("ui:index:${source.start}", "index", EtsTypes.NUMBER, source)
        val unused = EtsSymbol("ui:unused:${source.start}", "_unused", EtsTypes.NUMBER, source)
        val mapper = EtsLambda(listOf(EtsParameter(unused), EtsParameter(index)), listOf(EtsReturn(EtsReference(index), source)), EtsTypes.NUMBER, source)
        val array = EtsReference(EtsSymbol("arkui:Array", "Array", EtsNamedType("Array"), source, true))
        return call("from", listOf(record("ArrayLike", linkedMapOf("length" to count), owner), mapper), owner,
            result = EtsNamedType("Array", listOf(EtsTypes.NUMBER)), receiver = array)
    }

    private fun uiLambda(expression: IrExpression, scope: Scope, sourceName: String, axis: String? = null): EtsExpression {
        slotReceiver(expression, scope)?.let { return expression(it, scope) }
        val fn = lambda(expression, scope) ?: diagnostics.unsupported(expression, "Expected source content lambda")
        val captures = capturedValues(listOf(fn.body ?: diagnostics.unsupported(fn, "Missing slot body")), scope)
        val name = slotMethodName("${sourceName}_${fn.startOffset}")
        val captured = captures.map { capturedParameter(it, scope) }
        val child = scope.fork()
        captures.zip(captured).forEach { (symbol, parameter) -> child.bindings[symbol] = EtsReference(parameter.symbol) }
        val context = contextParameters(child, fn)
        val body = uiLambdaBodyWithAxis(expression, child, axis)
        // ArkUI only transforms UI DSL in builders/native slots, not arbitrary function arguments.
        val bridge = EtsFunction(name, context + captured, EtsTypes.VOID, body, language.source(fn), kind = EtsFunctionKind.METHOD, builder = true)
        slotMethods += bridge
        val callback = EtsLambda(context, listOf(EtsExpressionStatement(methodCall(bridge.symbol, context.map { EtsReference(it.symbol) } + captures.map { scope.bindings.getValue(it) }, fn))), EtsTypes.VOID, language.source(fn))
        return EtsNew(bindingWrappedBuilder(), listOf(callback), language.source(expression))
    }

    private fun capturedParameter(symbol: IrValueSymbol, scope: Scope): EtsParameter {
        val value = scope.bindings.getValue(symbol)
        return EtsParameter((value as? EtsReference)?.symbol ?: binding(symbol.owner, targetType = value.type).symbol)
    }

    private fun capturedValues(elements: List<IrElement>, scope: Scope): Set<IrValueSymbol> {
        val captures = linkedSetOf<IrValueSymbol>()
        val expanded = mutableSetOf<IrValueSymbol>()
        val visitor = object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element !in diagnostics.omittedUiElements) element.acceptChildrenVoid(this)
            }
            override fun visitGetValue(expression: IrGetValue) {
                if (expression in diagnostics.omittedUiElements) return
                val symbol = expression.symbol
                if (symbol in scope.aliases && expanded.add(symbol)) scope.aliases[symbol]!!.acceptVoid(this)
                else if (symbol in scope.bindings) captures += symbol
            }
        }
        elements.forEach { it.acceptVoid(visitor) }
        return captures
    }

    private fun bindInnerTextField(symbol: IrValueSymbol, field: EtsUiElement, scope: Scope, at: SourceSpan) {
        slots += symbol
        val inner = scope.fork()
        val context = contextParameters(inner, root)
        val name = slotMethodName("InnerTextField_${at.start}")
        val bridge = EtsFunction(name, context, EtsTypes.VOID, listOf(field), at,
            kind = EtsFunctionKind.METHOD, builder = true)
        slotMethods += bridge
        val callback = EtsLambda(context, listOf(EtsExpressionStatement(
            methodCall(bridge.symbol, context.map { EtsReference(it.symbol) }, root))), EtsTypes.VOID, at)
        scope.bindings[symbol] = EtsNew(bindingWrappedBuilder(), listOf(callback), at)
    }

    private fun uiLambdaBody(expression: IrExpression, scope: Scope): List<EtsStatement> {
        return uiLambdaBodyWithAxis(expression, scope, null)
    }

    private fun slotReceiver(expression: IrExpression?, scope: Scope): IrGetValue? {
        fun from(value: IrExpression?): IrGetValue? = when (value) {
            is IrGetValue -> when {
                value.symbol in slots -> value
                value.symbol in scope.aliases -> from(scope.aliases[value.symbol])
                else -> {
                    val owner = value.symbol.owner as? IrVariable
                    if (owner != null && !owner.isVar) from(owner.initializer) else null
                }
            }
            is IrTypeOperatorCall -> from(value.argument)
            is IrBlock -> from(value.statements.lastOrNull() as? IrExpression)
            else -> null
        }
        return from(expression) ?: from(dereference(expression, scope))
    }

    private fun uiLambdaBodyWithAxis(expression: IrExpression, scope: Scope, axis: String?): List<EtsStatement> {
        val slot = slotReceiver(expression, scope)
        if (slot != null)
            return listOf(EtsUiElement(call("builder", contextArguments(scope, expression), expression, receiver = expression(slot, scope))))
        val resolved = dereference(expression, scope)
        val fn = lambda(expression, scope) ?: diagnostics.unsupported(expression, "Expected composable content lambda")
        val extras = fn.valueParameters.filterNot { isLayoutScopeType(it.type) }
        if (extras.isNotEmpty() || fn.extensionReceiverParameter?.type?.let(::isLayoutScopeType) == false)
            diagnostics.unsupported(fn, "Unexpected content lambda parameters")
        val child = scope.fork()
        child.ambientValues.remove(LAYOUT_AXIS)
        if (axis != null) child.ambientValues[LAYOUT_AXIS] = literal(axis, expression)
        return uiBody(fn.body ?: diagnostics.unsupported(fn, "Missing content body"), child)
    }

    private fun provideMaterialContext(context: EtsExpression, content: IrExpression, scope: Scope,
        semanticFlags: Set<String>): List<EtsStatement> {
        val child = scope.fork()
        child.semanticFlags += semanticFlags
        val captures = capturedValues(listOf(content), scope)
        val captured = captures.map { capturedParameter(it, scope) }
        captures.zip(captured).forEach { (symbol, parameter) -> child.bindings[symbol] = EtsReference(parameter.symbol) }
        val parameters = contextParameters(child, content) + captured
        val at = language.source(content)
        val bridge = EtsFunction(slotMethodName("MaterialThemeContent_${at.start}"), parameters, EtsTypes.VOID,
            uiLambdaBody(content, child), at, kind = EtsFunctionKind.METHOD, builder = true)
        slotMethods += bridge
        return listOf(EtsUiElement(methodCall(bridge.symbol,
            contextArguments(scope, content, mapOf(MATERIAL_CONTEXT to context)) + captures.map { scope.bindings.getValue(it) }, content)))
    }

    private fun provideCompositionContext(values: List<Pair<ComposeCompositionLocalRule.Definition, EtsExpression>>,
        content: IrExpression, scope: Scope): List<EtsStatement> {
        val child = scope.fork()
        val captures = capturedValues(listOf(content), scope)
        val captured = captures.map { capturedParameter(it, scope) }
        captures.zip(captured).forEach { (symbol, parameter) -> child.bindings[symbol] = EtsReference(parameter.symbol) }
        val at = language.source(content)
        val context = contextParameters(child, content)
        val provided = values.mapIndexed { index, (_, value) -> EtsParameter(EtsSymbol(
            "compose:provided:${at.file}:${at.start}:$index", "__etsProvidedValue$index", value.type, at)) }
        val overrides = linkedMapOf<ComposeCompositionLocalRule.Definition, EtsExpression>()
        values.zip(provided).forEach { (value, parameter) -> overrides[value.first] = EtsReference(parameter.symbol) }
        child.ambientValues[COMPOSITION_CONTEXT] = compositionLocals.overriddenContext(
            compositionContext(child, at), overrides, at)
        val parameters = context + provided + captured
        val bridge = EtsFunction(slotMethodName("CompositionLocalContent_${at.start}"), parameters, EtsTypes.VOID,
            uiLambdaBody(content, child), at, kind = EtsFunctionKind.METHOD, builder = true)
        slotMethods += bridge
        val arguments = contextArguments(scope, content) + values.map { it.second } + captures.map { scope.bindings.getValue(it) }
        return listOf(EtsUiElement(methodCall(bridge.symbol, arguments, content)))
    }

    private fun slotMethodName(stem: String): String {
        var name = stem
        var index = 2
        while (!slotMethodNames.add(name)) name = "${stem}_${index++}"
        return name
    }

    private fun surfaceContent(content: IrExpression, scope: Scope, axis: String? = null): EtsExpression {
        val slot = uiLambda(content, scope, "SurfaceContent", axis)
        val at = language.source(content)
        val args = contextArguments(scope, content)
        val member = EtsMember(slot, "builder", EtsFunctionType(args.map { it.type }, EtsTypes.VOID), at)
        return if (args.isEmpty()) member else EtsLambda(emptyList(),
            listOf(EtsExpressionStatement(EtsCall(member, args, EtsTypes.VOID, at))), EtsTypes.VOID, at)
    }

    private fun constraintsContent(content: IrExpression, scope: Scope): ConstraintContent {
        val fn = lambda(content, scope) ?: diagnostics.unsupported(content, "Expected BoxWithConstraints content lambda")
        val receiver = fn.extensionReceiverParameter ?: fn.valueParameters.singleOrNull()
            ?: diagnostics.unsupported(fn, "BoxWithConstraints content requires its constraint receiver")
        val at = language.source(content)
        val child = scope.fork()
        child.ambientValues.remove(LAYOUT_AXIS)
        val captures = capturedValues(listOf(fn.body!!), scope).filter { it != receiver.symbol }
        val context = boundContextParameters(child, fn)
        val captureParameters = captures.map { capturedParameter(it, scope) }
        val values = (context.map { it.parameter.symbol } + captureParameters.map { it.symbol })
            .zip(contextArguments(scope, content) + captures.map { scope.bindings.getValue(it) })
        val bindings = values.mapIndexed { index, (_, value) -> "value$index" to value }.toMap()
        val dataName = slotMethodName("ConstraintData_${at.start}")
        val dataType = etsClassSymbol(dataName, at).type as EtsNamedType
        val dataParameters = bindings.map { (name, value) -> EtsParameter(EtsSymbol("ui:constraintData:${at.start}:$name", name, value.type, at)) }
        val dataThis = EtsReference(EtsSymbol("ui:constraintData:${at.start}:this", "this", dataType, at, external = true))
        val constructor = EtsFunction("constructor", dataParameters, EtsTypes.VOID, dataParameters.map {
            EtsExpressionStatement(EtsAssignment(EtsMember(dataThis, it.symbol.name, it.symbol.type, at), EtsReference(it.symbol), at))
        }, at, kind = EtsFunctionKind.CONSTRUCTOR)
        constraintDataClasses += EtsClass(dataName, dataParameters.map { EtsField(it.symbol, readonly = true) } + constructor, at)
        val data = EtsNew(dataType, bindings.values.toList(), at)
        val argsType = boxConstraintsArgsType
        val args = EtsReference(EtsSymbol("ui:constraintArgs:${at.start}", "args", argsType, at))
        child.bindings[receiver.symbol] = EtsMember(args, "bounds", boxConstraintsBindingType, at)
        // ArkUI structs cannot be generic. This paired builder/data envelope erases
        // only the native component boundary, then restores its generated class.
        val dataRead = EtsCast(EtsMember(args, "data", EtsTypes.OBJECT, at), dataType, at)
        values.forEachIndexed { index, (symbol, _) ->
            val value = EtsMember(dataRead, "value$index", symbol.type, at)
            if (index < context.size) child.ambientValues[context[index].contract.identity] = value
            else child.bindings[captures[index - context.size]] = value
        }
        val body = uiBody(fn.body!!, child)
        val alignment = EtsMember(args, "alignment", EtsNamedType("Alignment"), at)
        val bridge = EtsFunction(slotMethodName("BoxWithConstraintsContent_${at.start}"), listOf(EtsParameter(args.symbol, reactiveInput = true)), EtsTypes.VOID,
            listOf(native("Stack", listOf(record("StackOptions", linkedMapOf("alignContent" to alignment), fn)), fn, body)), at,
            kind = EtsFunctionKind.FUNCTION, builder = true)
        constraintBuilders += bridge
        val builderType = EtsNamedType("WrappedBuilder", listOf(EtsTupleType(listOf(argsType))))
        return ConstraintContent(EtsNew(builderType, listOf(EtsReference(bridge.symbol)), at), data)
    }

    private fun callback(expression: IrExpression, scope: Scope): EtsExpression {
        val fn = lambda(expression, scope) ?: return expression(expression, scope)
        val body = fn.body ?: diagnostics.unsupported(fn, "Missing callback body")
        return EtsLambda(emptyList(), language.statements(body, scope.fork()), EtsTypes.VOID, language.source(expression))
    }

    private fun platformCall(call: IrCall, scope: Scope): EtsExpression? {
        val function = call.symbol.owner
        val api = symbolName(function)
        if (isUiBuilder(function) && sourceFile(function) != null && !function.isExternal)
            diagnostics.unsupported(call, "Source UI builder cannot execute inside a value helper or ordinary expression")
        val property = function.correspondingPropertySymbol?.owner?.let(::symbolName)
        val receiver = dereference(call.dispatchReceiver ?: call.extensionReceiver, scope)
        val value = receiver as? IrGetValue
        if (property in setOf("androidx.compose.runtime.State.value", "androidx.compose.runtime.MutableState.value")) {
            val field = value?.symbol?.let(states::get) ?: diagnostics.unsupported(call, "State access requires source remembered state")
            return if (function.valueParameters.isEmpty()) field(field, language.type(call.type), call)
                else {
                    val assigned = language.expression(call.getValueArgument(0)!!, scope)
                    etsDiscard(EtsAssignment(field(field, assigned.type, call), assigned, language.source(call)))
                }
        }
        if (property == "androidx.compose.foundation.pager.PagerState.currentPage") {
            val pager = pagerFor(receiver, scope, call)
            return field("${pager.name}_currentPage", EtsTypes.NUMBER, call)
        }
        if (api == "kotlinx.coroutines.launch")
            diagnostics.unsupported(call, "Unsupported resolved platform expression: $api")
        return null
    }

    private fun platformStatement(call: IrCall, scope: Scope): List<EtsStatement>? {
        val api = symbolName(call.symbol.owner)
        if (api == "kotlinx.coroutines.launch") {
            val value = dereference(call.dispatchReceiver ?: call.extensionReceiver, scope) as? IrGetValue
            if (value?.symbol !in coroutineScopes) diagnostics.unsupported(call, "launch requires remembered UI coroutine scope")
            checkArguments(call, setOf("block"))
            val target = singleResult(argument(call, "block"), scope, call) as? IrCall
                ?: diagnostics.unsupported(call, "Pager adapter supports only launch { pager.animateScrollToPage(...) }")
            if (symbolName(target.symbol.owner) != "androidx.compose.foundation.pager.PagerState.animateScrollToPage")
                diagnostics.unsupported(target, "Unsupported coroutine operation in Pager adapter")
            checkArguments(target, setOf("page"))
            val pager = pagerFor(target.dispatchReceiver, scope, target)
            val page = argument(target, "page") ?: diagnostics.unsupported(target, "Missing pager target index")
            val source = language.source(call)
            val controller = field("${pager.name}_controller", EtsNamedType("SwiperController"), call)
            val method = EtsMember(controller, "changeIndex",
                EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.BOOLEAN), EtsTypes.VOID), source)
            return listOf(EtsExpressionStatement(EtsCall(method, listOf(language.expression(page, scope),
                EtsLiteral(true, EtsTypes.BOOLEAN, source)), EtsTypes.VOID, source)))
        }
        return null
    }

    private fun pagerFor(expression: IrExpression?, scope: Scope, owner: IrElement): Pager {
        val value = dereference(expression, scope) as? IrGetValue
        return value?.symbol?.let(pagers::get) ?: diagnostics.unsupported(owner, "Expected source remembered PagerState")
    }

    private fun isLayoutScopeType(type: IrType): Boolean {
        val name = type.classFqName?.asString()
            ?: type.classOrNull?.owner?.let(::symbolName) ?: return false
        return name in setOf("androidx.compose.foundation.layout.RowScope",
            "androidx.compose.foundation.layout.ColumnScope",
            "androidx.compose.foundation.layout.BoxScope")
    }

    private fun isLayoutScopeReceiver(value: IrExpression): Boolean = isLayoutScopeType(value.type)

    private fun isContentSlotType(type: IrType): Boolean {
        val simple = (if (type is IrSimpleType && type.nullability == SimpleTypeNullability.MARKED_NULLABLE)
            type.makeNotNull() else type) as? IrSimpleType ?: return false
        val name = simple.classOrNull?.owner?.let(::symbolName) ?: return false
        if (name == "kotlin.Function0") return true
        if (name != "kotlin.Function1") return false
        val arguments = simple.arguments.mapNotNull { (it as? IrTypeProjection)?.type }
        return arguments.size == 2 && arguments[1].isUnit() && isLayoutScopeType(arguments[0])
    }

    private fun dereference(expression: IrExpression?, scope: Scope): IrExpression? =
        if (expression is IrGetValue && expression.symbol in scope.aliases) dereference(scope.aliases[expression.symbol], scope)
        else expression

    private fun checkArguments(call: IrCall, supported: Set<String>) = target.checkArguments(call, supported)

    private fun dimension(expression: IrExpression, scope: Scope, unit: String): EtsExpression {
        val expected = if (unit == "dp") "androidx.compose.ui.unit.Dp" else "androidx.compose.ui.unit.TextUnit"
        if (expression.type.classOrNull?.owner?.let(::symbolName) != expected)
            diagnostics.unsupported(expression, "Expected resolved $unit dimension")
        val emitted = language.expression(expression, scope)
        return if (unit == "dp") requireSpecifiedDp(emitted, language.source(expression), "Compose dimension consumer")
        else emitted
    }

    private fun isUnspecifiedDp(value: IrExpression, scope: Scope): Boolean {
        val resolved = dereference(value, scope) ?: return false
        val property = when (resolved) {
            is IrCall -> resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            is IrGetField -> resolved.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                ?: symbolName(resolved.symbol.owner)
            else -> null
        }
        return property == "androidx.compose.ui.unit.Dp.Companion.Unspecified"
    }

    private fun stableDimension(value: IrExpression, emitted: EtsExpression, scope: Scope): Boolean {
        if (emitted is EtsLiteral || stableRead(value, scope)) return true
        val getter = dereference(value, scope) as? IrCall ?: return false
        val property = getter.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property in setOf("minWidth", "minHeight", "maxWidth", "maxHeight").map {
                "androidx.compose.foundation.layout.BoxWithConstraintsScope.$it" })
            return getter.dispatchReceiver?.let { stableRead(it, scope) } == true
        return property in setOf("androidx.compose.ui.unit.dp", "androidx.compose.ui.unit.sp") &&
            getter.extensionReceiver?.let { stableRead(it, scope) } == true
    }

    private fun colorValue(expression: IrExpression, scope: Scope): EtsExpression {
        return requireSpecifiedColor(language.expression(expression, scope), language.source(expression),
            "Compose color consumer")
    }

    // Structural aliases are safe only when their construction has no user effects.
    private fun stableModifier(value: IrExpression, scope: Scope): Boolean {
        val resolved = dereference(value, scope) ?: return false
        if (resolved is IrBlock) return (resolved.statements.singleOrNull() as? IrExpression)?.let { stableModifier(it, scope) } == true
        if (resolved is IrGetObjectValue) return symbolName(resolved.symbol.owner) == "androidx.compose.ui.Modifier.Companion"
        if (resolved is IrWhen) return resolved.branches.all {
            (it is IrElseBranch || stableRead(it.condition, scope)) && stableModifier(it.result, scope)
        }
        if (resolved !is IrCall || sourceFile(resolved.symbol.owner) != null) return false
        if (symbolName(resolved.symbol.owner) !in setOf("androidx.compose.foundation.verticalScroll",
                "androidx.compose.foundation.horizontalScroll", "androidx.compose.ui.Modifier.then")) return false
        if (!stableModifier(resolved.extensionReceiver ?: resolved.dispatchReceiver ?: return false, scope)) return false
        return resolved.symbol.owner.valueParameters.indices.mapNotNull(resolved::getValueArgument).all {
            val arg = dereference(it, scope)
            stableRead(it, scope) || arg is IrCall && symbolName(arg.symbol.owner) == "androidx.compose.foundation.rememberScrollState" &&
                arg.symbol.owner.valueParameters.indices.mapNotNull(arg::getValueArgument).all { input -> stableRead(input, scope) } ||
                arg != null && stableModifier(arg, scope)
        }
    }

    private fun modifiers(expression: IrExpression?, initialScope: Scope, node: ComposeElement): List<EtsStatement> =
        modifiers(expression, initialScope, node, emptyMap())

    private fun modifierBounds(expression: IrExpression?, initialScope: Scope): Set<String> {
        val scope = initialScope.fork()
        var width = false
        var height = false
        val operations = mutableListOf<IrCall>()
        fun collect(value: IrExpression?) {
            when (val resolved = dereference(value, scope)) {
                null, is IrGetObjectValue -> Unit
                is IrGetValue -> Unit
                is IrCall -> {
                    collect(resolved.extensionReceiver ?: resolved.dispatchReceiver)
                    if (symbolName(resolved.symbol.owner) == "androidx.compose.ui.Modifier.then")
                        collect(argument(resolved, "other"))
                    else operations += resolved
                }
                is IrBlock -> {
                    for (statement in resolved.statements.dropLast(1)) {
                        val variable = statement as? IrVariable ?: continue
                        variable.initializer?.let { scope.aliases[variable.symbol] = it }
                    }
                    collect(resolved.statements.lastOrNull() as? IrExpression)
                }
                else -> Unit
            }
        }
        collect(expression)
        operations.forEach { call ->
            when (symbolName(call.symbol.owner)) {
                "androidx.compose.foundation.layout.width", "androidx.compose.foundation.layout.fillMaxWidth" -> width = true
                "androidx.compose.foundation.layout.height", "androidx.compose.foundation.layout.fillMaxHeight" -> height = true
                "androidx.compose.foundation.layout.size", "androidx.compose.foundation.layout.fillMaxSize" -> {
                    width = true; height = true
                }
                "androidx.compose.foundation.layout.aspectRatio" -> {
                    if (width) height = true else if (height) width = true
                }
            }
        }
        return buildSet {
            if (width) add(BOUNDED_WIDTH)
            if (height) add(BOUNDED_HEIGHT)
        }
    }

    private fun modifiers(expression: IrExpression?, initialScope: Scope, node: ComposeElement,
        choices: Map<IrWhen, IrExpression>): List<EtsStatement> {
        val scope = initialScope.fork()
        val operations = mutableListOf<IrCall>()
        var choice: IrWhen? = null
        fun stableNamedValue(value: IrExpression): Boolean {
            val resolved = dereference(value, scope) ?: return false
            if (stableRead(resolved, scope) || isConstraintDimensionRead(resolved, scope) || stableModifier(resolved, scope)) return true
            if (resolved is IrGetObjectValue && symbolName(resolved.symbol.owner) in
                setOf("androidx.compose.ui.Modifier.Companion", "androidx.compose.ui.Modifier")) return true
            if (resolved is IrCall && sourceFile(resolved.symbol.owner) == null &&
                resolved.type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.ui.Modifier") {
                val receiver = resolved.extensionReceiver ?: resolved.dispatchReceiver ?: return false
                return stableNamedValue(receiver) && resolved.symbol.owner.valueParameters.indices
                    .mapNotNull { resolved.getValueArgument(it) }.all(::stableNamedValue)
            }
            return try {
                when (val emitted = language.expression(resolved, scope)) {
                    is EtsLiteral -> true
                    is EtsMember -> emitted.type == EtsTypes.NUMBER ||
                        (emitted.receiver as? EtsReference)?.symbol?.id in
                            setOf("arkui:Alignment", "arkui:HorizontalAlign", "arkui:VerticalAlign")
                    is EtsReference, is EtsBinary, is EtsConditional -> emitted.type == EtsTypes.NUMBER
                    else -> false
                }
            } catch (_: Unsupported) { false }
        }
        fun collect(value: IrExpression?) {
            when (val resolved = dereference(value, scope)) {
                null -> return
                is IrGetObjectValue -> if (symbolName(resolved.symbol.owner) !in setOf("androidx.compose.ui.Modifier.Companion", "androidx.compose.ui.Modifier"))
                    diagnostics.unsupported(resolved, "Expected Modifier companion")
                is IrGetValue -> if (scope.bindings[resolved.symbol]?.type != emptyModifierType)
                    diagnostics.unsupported(resolved, "Unsupported bound Modifier value")
                is IrWhen -> {
                    val selected = choices[resolved]
                    if (selected != null) collect(selected)
                    else if (choice == null) choice = resolved
                }
                is IrCall -> {
                    collect(resolved.extensionReceiver ?: resolved.dispatchReceiver)
                    if (symbolName(resolved.symbol.owner) == "androidx.compose.ui.Modifier.then")
                        collect(argument(resolved, "other"))
                    else operations += resolved
                }
                is IrBlock -> {
                    // Kotlin wraps reordered named arguments in a block of temporaries.
                    // Alias only stable reads/constants; never duplicate or reorder effects.
                    resolved.statements.dropLast(1).forEach { statement ->
                        val variable = statement as? IrVariable
                        val initial = variable?.initializer
                        if (variable == null || variable.isVar || initial == null ||
                            variable.origin != IrDeclarationOrigin.IR_TEMPORARY_VARIABLE)
                            diagnostics.unsupported(statement, "Unsupported statement in Modifier argument block")
                        if (!stableNamedValue(initial)) diagnostics.unsupported(initial,
                            "Named Modifier arguments require stable values to preserve evaluation order")
                        scope.aliases[variable.symbol] = initial
                    }
                    collect(resolved.statements.lastOrNull() as? IrExpression
                        ?: diagnostics.unsupported(resolved, "Modifier argument block requires a result"))
                }
                else -> diagnostics.unsupported(resolved, "Unsupported Modifier receiver")
            }
        }
        collect(expression)
        choice?.let { conditional ->
            if (!stableModifier(conditional, scope)) diagnostics.unsupported(conditional,
                "Conditional Modifier requires stable conditions and effect-free construction")
            return listOf(EtsIf(conditional.branches.map { branch -> EtsBranch(
                if (branch is IrElseBranch) null else language.expression(branch.condition, scope),
                modifiers(expression, scope, node, choices + (conditional to branch.result))) }, language.source(conditional)))
        }
        val scrolling = ScrollModifier(target, language)
        val weights = operations.filter(::isWeightModifier)
        if (weights.size > 1) diagnostics.unsupported(weights[1], "Repeated weight modifiers require parent-data ordering support")
        val weight = weights.singleOrNull()?.let { call ->
            checkArguments(call, setOf("weight", "fill"))
            val fill = argument(call, "fill")
            if (fill != null && (expression(fill, scope) as? EtsLiteral)?.value != true)
                diagnostics.unsupported(fill, "weight currently requires fill=true")
            val value = argument(call, "weight") ?: diagnostics.unsupported(call, "Missing weight")
            val emitted = expression(value, scope)
            if (emitted !is EtsLiteral && !stableRead(value, scope))
                diagnostics.unsupported(value, "weight requires an immutable scalar to preserve evaluation order")
            layoutWeight(emitted, language.source(value))
        }
        operations.removeAll(weights.toSet())
        val weightAxis = if (weight != null) (scope.ambientValues[LAYOUT_AXIS] as? EtsLiteral)?.value as? String else null
        if (weight != null && weightAxis == null)
            diagnostics.unsupported(weights.single(), "weight requires a known Row or Column parent; content slot parent is unresolved")
        val owner = expression ?: root
        val ambientTypes = setOf(materialContextType, materialColorSchemeType, materialColorValuesType, typographyType, textStyleType)
        fun stableArgument(value: EtsExpression): Boolean = when (value) {
            is EtsLiteral -> true
            is EtsReference -> value.type in ambientTypes ||
                scope.bindings.any { (symbol, binding) ->
                binding == value && when (val declaration = symbol.owner) {
                    is IrVariable -> !declaration.isVar
                    is IrValueParameter -> true
                    else -> false
                }
            }
            is EtsMember -> (value.receiver as? EtsReference)?.symbol?.id in
                setOf("arkui:Alignment", "arkui:HorizontalAlign", "arkui:VerticalAlign") ||
                ((value.type == EtsTypes.NUMBER || value.type in ambientTypes) &&
                    stableArgument(value.receiver))
            is EtsNew -> value.classType in ambientTypes && value.arguments.all(::stableArgument)
            is EtsBinary -> stableArgument(value.left) && stableArgument(value.right)
            is EtsUnary -> stableArgument(value.operand)
            is EtsConditional -> stableArgument(value.condition) && stableArgument(value.whenTrue) && stableArgument(value.whenFalse)
            is EtsObject -> value.fields.values.all(::stableArgument)
            is EtsArray -> value.elements.all(::stableArgument)
            is EtsLambda -> true
            else -> false
        }
        val requiresArgumentOrder = node.orderedArguments.any { !stableArgument(it) }
        fun layer(index: Int, width: Boolean, height: Boolean): EtsUiElement {
            val attributes = linkedMapOf<String, EtsExpression>()
            if (width) attributes["width"] = literal("100%", owner)
            if (height) attributes["height"] = literal("100%", owner)
            var nextWidth = width
            var nextHeight = height
            val seen = mutableSetOf<String>()
            var cursor = index
            var wrap: WrapContent? = null
            var scroll: IrCall? = null
            while (cursor < operations.size) {
                val call = operations[cursor]
                if (scrolling.axis(call) != null) {
                    scroll = call
                    cursor++
                    break
                }
                wrap = wrapContent(call, language, scope, target)
                if (wrap != null) {
                    if (wrap.width) nextWidth = false
                    if (wrap.height) nextHeight = false
                    cursor++
                    break
                }
                val api = symbolName(call.symbol.owner)
                val keys = when (api) {
                    "androidx.compose.foundation.layout.width", "androidx.compose.foundation.layout.fillMaxWidth" -> setOf("width")
                    "androidx.compose.foundation.layout.height", "androidx.compose.foundation.layout.fillMaxHeight" -> setOf("height")
                    "androidx.compose.foundation.layout.fillMaxSize", "androidx.compose.foundation.layout.size" -> setOf("width", "height")
                    "androidx.compose.foundation.layout.heightIn", "androidx.compose.foundation.layout.widthIn",
                    "androidx.compose.foundation.layout.sizeIn" -> setOf("constraintSize")
                    "androidx.compose.foundation.layout.padding" -> setOf("padding")
                    "androidx.compose.foundation.background" -> if (argument(call, "shape") == null) setOf("backgroundColor")
                        else setOf("backgroundColor", "borderRadius")
                    "androidx.compose.ui.draw.clip" -> setOf("borderRadius", "clip", "clipShape")
                    "androidx.compose.ui.platform.testTag" -> setOf("id")
                    "androidx.compose.foundation.clickable" -> setOf("onClick", "enabled")
                    "androidx.compose.ui.input.pointer.pointerInput" -> setOf("hitTestBehavior")
                    "androidx.compose.foundation.layout.offset" -> setOf("offset")
                    "androidx.compose.ui.draw.rotate" -> setOf("rotate")
                    "androidx.compose.foundation.layout.aspectRatio" -> setOf("aspectRatio")
                    else -> {
                        diagnostics.omitUi(call, "Unsupported resolved Modifier API: $api", api,
                            "omitted_modifier", "Modifier arguments and behavior are omitted; other modifier operations remain.",
                            (0 until call.valueArgumentsCount).mapNotNull(call::getValueArgument))
                        cursor++
                        continue
                    }
                }
                // Padding changes the next operation's coordinate space. Repeated attributes
                // must also keep their own layer instead of overwriting an earlier operation.
                if ("padding" in seen || keys.any { it in seen }) break
                if (api == "androidx.compose.ui.draw.clip" && "backgroundColor" in seen) break
                when (api) {
                    "androidx.compose.foundation.layout.size" -> {
                        checkArguments(call, setOf("size", "width", "height"))
                        for (name in listOf("width", "height")) {
                            val value = argument(call, "size") ?: argument(call, name)
                                ?: diagnostics.unsupported(call, "Missing size $name")
                            val emitted = dimension(value, scope, "dp")
                            if (!stableDimension(value, emitted, scope)) diagnostics.unsupported(value,
                                "size currently requires stable dimensions to preserve evaluation count")
                            if (name == "width") {
                                if (!nextWidth) attributes[name] = emitted
                                nextWidth = true
                            } else {
                                if (!nextHeight) attributes[name] = emitted
                                nextHeight = true
                            }
                        }
                    }
                    "androidx.compose.foundation.layout.width", "androidx.compose.foundation.layout.height" -> {
                        val name = keys.single()
                        checkArguments(call, setOf(name))
                        val value = argument(call, name) ?: diagnostics.unsupported(call, "Missing $name")
                        val emitted = dimension(value, scope, "dp")
                        val constrained = if (name == "width") nextWidth else nextHeight
                        if (!constrained) attributes[name] = emitted
                        else {
                            if (!stableDimension(value, emitted, scope)) diagnostics.unsupported(value,
                                "A size already fixed by an outer modifier requires a stable scalar argument")
                        }
                        if (name == "width") nextWidth = true else nextHeight = true
                    }
                    "androidx.compose.foundation.layout.heightIn", "androidx.compose.foundation.layout.widthIn",
                    "androidx.compose.foundation.layout.sizeIn" -> {
                        checkArguments(call, setOf("min", "max", "minWidth", "maxWidth", "minHeight", "maxHeight"))
                        val bounds = linkedMapOf<String, EtsExpression>()
                        fun bound(sourceName: String, targetName: String) {
                            val value = argument(call, sourceName) ?: return
                            if (isUnspecifiedDp(value, scope)) return
                            val emitted = dimension(value, scope, "dp")
                            if (!stableDimension(value, emitted, scope)) diagnostics.unsupported(value,
                                "Size bounds currently require stable dimensions to preserve evaluation count")
                            bounds[targetName] = emitted
                        }
                        when (api) {
                            "androidx.compose.foundation.layout.heightIn" -> {
                                bound("min", "minHeight"); bound("max", "maxHeight")
                            }
                            "androidx.compose.foundation.layout.widthIn" -> {
                                bound("min", "minWidth"); bound("max", "maxWidth")
                            }
                            else -> {
                                bound("minWidth", "minWidth"); bound("maxWidth", "maxWidth")
                                bound("minHeight", "minHeight"); bound("maxHeight", "maxHeight")
                            }
                        }
                        if (bounds.isNotEmpty()) attributes["constraintSize"] = record("ConstraintSizeOptions", bounds, call)
                    }
                    "androidx.compose.foundation.layout.fillMaxWidth", "androidx.compose.foundation.layout.fillMaxHeight", "androidx.compose.foundation.layout.fillMaxSize" -> {
                        checkArguments(call, setOf("fraction"))
                        val fraction = argument(call, "fraction")
                        if (fraction != null && !stableRead(fraction, scope))
                            diagnostics.unsupported(fraction, "Fill fraction currently requires a stable scalar argument")
                        val source = language.source(call)
                        val length = fraction?.let {
                            EtsBinary("+", EtsBinary("*", language.expression(it, scope),
                                EtsLiteral(100, EtsTypes.NUMBER, source), EtsTypes.NUMBER, source),
                                EtsLiteral("%", EtsTypes.STRING, source), EtsTypes.STRING, source)
                        } ?: EtsLiteral("100%", EtsTypes.STRING, source)
                        if ("width" in keys) { if (!nextWidth) attributes["width"] = length; nextWidth = true }
                        if ("height" in keys) { if (!nextHeight) attributes["height"] = length; nextHeight = true }
                    }
                    "androidx.compose.foundation.layout.padding" -> {
                        checkArguments(call, setOf("all", "horizontal", "vertical", "start", "top", "end", "bottom"))
                        fun edge(name: String) = argument(call, name)?.let { dimension(it, scope, "dp") } ?: literal(0, call)
                        attributes["padding"] = if (argument(call, "all") != null) edge("all")
                        else if (call.symbol.owner.valueParameters.any { it.name.asString() == "horizontal" }) {
                            val horizontal = edge("horizontal")
                            val vertical = edge("vertical")
                            val stable = listOf("horizontal" to horizontal, "vertical" to vertical).all { (name, emitted) ->
                                argument(call, name)?.let { stableDimension(it, emitted, scope) } != false
                            }
                            if (stable) record("Padding", linkedMapOf("left" to horizontal, "right" to horizontal,
                                "top" to vertical, "bottom" to vertical), call)
                            else symmetricPadding(horizontal, vertical, language.source(call))
                        }
                        else record("Padding", linkedMapOf("left" to edge("start"), "right" to edge("end"), "top" to edge("top"), "bottom" to edge("bottom")), call)
                    }
                    "androidx.compose.foundation.background" -> {
                        checkArguments(call, setOf("color", "shape"))
                        val color = argument(call, "color") ?: diagnostics.unsupported(call, "Missing background color")
                        attributes["backgroundColor"] = requireSpecifiedColor(language.expression(color, scope),
                            language.source(color), "Modifier.background")
                        argument(call, "shape")?.let { attributes["borderRadius"] =
                            shapes.borderRadius(it, language, scope, diagnostics) }
                    }
                    "androidx.compose.ui.draw.clip" -> {
                        checkArguments(call, setOf("shape"))
                        val shape = argument(call, "shape") ?: diagnostics.unsupported(call, "Missing clip shape")
                        val cut = shapes.cutClip(shape, attributes["width"], attributes["height"], diagnostics)
                        if (cut != null) attributes["clipShape"] = cut else {
                            attributes["borderRadius"] = shapes.borderRadius(shape, language, scope, diagnostics)
                            attributes["clip"] = literal(true, call)
                        }
                    }
                    "androidx.compose.ui.platform.testTag" -> {
                        checkArguments(call, setOf("tag"))
                        attributes["id"] = expression(argument(call, "tag")!!, scope)
                    }
                    "androidx.compose.foundation.clickable" -> {
                        if (node.touch == null) diagnostics.unsupported(call,
                            "Minimum touch target arbitration requires a homogeneous Row/repeat/Box group")
                        checkArguments(call, setOf("onClick", "enabled"))
                        attributes["onClick"] = callback(argument(call, "onClick")!!, scope)
                        argument(call, "enabled")?.let { attributes["enabled"] = expression(it, scope) }
                    }
                    "androidx.compose.ui.input.pointer.pointerInput" -> {
                        attributes["hitTestBehavior"] = PointerInputModifier(target).value(call) { stableRead(it, scope) }
                    }
                    "androidx.compose.foundation.layout.offset" -> {
                        checkArguments(call, setOf("x", "y"))
                        if (argument(call, "x") == null && argument(call, "y") == null)
                            diagnostics.unsupported(call, "offset currently requires x/y Dp")
                        fun axis(name: String) = argument(call, name)?.let { dimension(it, scope, "dp") } ?: literal(0, call)
                        val x = axis("x")
                        val y = axis("y")
                        listOf("x" to x, "y" to y).forEach { (name, emitted) ->
                            val value = argument(call, name) ?: return@forEach
                            if (!stableDimension(value, emitted, scope)) diagnostics.unsupported(value,
                                "offset currently requires stable dimensions to preserve evaluation count")
                        }
                        attributes["offset"] = record("Position", linkedMapOf("x" to x, "y" to y), call)
                    }
                    "androidx.compose.ui.draw.rotate" -> {
                        checkArguments(call, setOf("degrees"))
                        val degrees = argument(call, "degrees") ?: diagnostics.unsupported(call, "Missing rotation degrees")
                        val emitted = expression(degrees, scope)
                        fun constantNumber(value: EtsExpression): Boolean = when (value) {
                            is EtsLiteral -> value.value is Number
                            is EtsUnary -> value.operator in setOf("-", "+") && constantNumber(value.operand)
                            is EtsCall -> {
                                val member = value.callee as? EtsMember
                                member?.name == "fround" &&
                                    (member.receiver as? EtsReference)?.symbol?.name == "Math" &&
                                    value.arguments.singleOrNull()?.let(::constantNumber) == true
                            }
                            else -> false
                        }
                        if (!constantNumber(emitted) && !stableRead(degrees, scope))
                            diagnostics.unsupported(degrees, "rotate currently requires a stable scalar argument")
                        attributes["rotate"] = record("RotateOptions", linkedMapOf("angle" to emitted), call)
                    }
                    "androidx.compose.foundation.layout.aspectRatio" -> {
                        checkArguments(call, setOf("ratio", "matchHeightConstraintsFirst"))
                        val heightFirst = argument(call, "matchHeightConstraintsFirst")
                        if (heightFirst != null && (expression(heightFirst, scope) as? EtsLiteral)?.value != false)
                            diagnostics.unsupported(heightFirst, "aspectRatio currently requires matchHeightConstraintsFirst=false")
                        val ratio = argument(call, "ratio")
                            ?: diagnostics.unsupported(call, "Missing aspectRatio ratio")
                        val emitted = expression(ratio, scope)
                        if (emitted !is EtsLiteral && !stableRead(ratio, scope))
                            diagnostics.unsupported(ratio, "aspectRatio requires a stable scalar value")
                        attributes["aspectRatio"] = emitted
                        if (nextWidth) nextHeight = true else if (nextHeight) nextWidth = true
                    }
                }
                if ("aspectRatio" in attributes) {
                    if (nextWidth) nextHeight = true else if (nextHeight) nextWidth = true
                }
                seen += keys
                cursor++
            }
            val attrs = attributes.map { (name, value) -> attribute(name, listOf(value), owner) }.toMutableList()
            // Native attributes may execute after constructor arguments and child builders.
            // Do not move an unknown read/call across another unknown modifier expression.
            if (requiresArgumentOrder && attributes.values.any { !stableArgument(it) })
                diagnostics.unsupported(owner,
                    "UI argument evaluation order requires stable modifier values or an immutable alignment binding")
            if (weight != null && attributes.values.any { !stableArgument(it) })
                diagnostics.unsupported(owner, "Weighted modifiers require stable sibling arguments to preserve evaluation order")
            node.touch?.let { touch ->
                val origin = operations.take(index).sumOf { touch.padding[it] ?: 0.0 }
                if (index == 0) {
                    if ("id" in attributes && touch.count != 1) diagnostics.unsupported(touch.box,
                        "Touch target source tag must be inside its outer padding boundary")
                    val item = scope.bindings[touch.index.symbol]
                        ?: diagnostics.unsupported(touch.box, "Unbound repeated touch target index")
                    if ("id" !in attributes) attrs += attribute("id", listOf(EtsBinary("+", literal("__etsTouch${touch.box.startOffset}_", touch.box), item, EtsTypes.STRING, language.source(touch.box))), touch.box)
                }
                attrs += attribute("responseRegion", listOf(touch.region(origin, language.source(touch.box))), touch.box)
                attrs += attribute("mouseResponseRegion", listOf(record("Rectangle", linkedMapOf("x" to literal(0, touch.box), "y" to literal(0, touch.box),
                    "width" to literal("100%", touch.box), "height" to literal("100%", touch.box)), touch.box)), touch.box)
            }
            if (scroll != null) {
                val axis = scrolling.axis(scroll)
                val child = layer(cursor, if (axis == "width") false else nextWidth,
                    if (axis == "height") false else nextHeight)
                return native("Scroll", emptyList(), scroll, listOf(child)).copy(
                    attributes = scrolling.attributes(scroll, scope) + attrs)
            }
            if (wrap == null && cursor == operations.size && node.requiresBoundedSize && (!nextWidth || !nextHeight))
                diagnostics.unsupported(owner, "Asynchronous image loading requires bounded width and height; intrinsic-size negotiation is not yet supported")
            if (wrap == null && cursor == operations.size && seen.none { it in node.modifierBoundaries })
                return node.element.copy(attributes = node.element.attributes + attrs)
            val options = wrap?.let { record("StackOptions", linkedMapOf("alignContent" to it.alignment), owner) } ?: stackOptions(owner)
            return native("Stack", listOf(options), owner, listOf(layer(cursor, nextWidth, nextHeight))).copy(attributes = attrs)
        }
        val result = layer(0, weightAxis == "width" || node.requiresBoundedSize && BOUNDED_WIDTH in scope.semanticFlags,
            weightAxis == "height" || node.requiresBoundedSize && BOUNDED_HEIGHT in scope.semanticFlags)
        return listOf(if (weight == null) result else result.copy(attributes = result.attributes +
            attribute("layoutWeight", listOf(weight), owner)))
    }

    companion object {
        private val COMPOSABLE = FqName("androidx.compose.runtime.Composable")
    }
}
