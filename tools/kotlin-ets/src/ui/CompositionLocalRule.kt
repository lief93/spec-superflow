@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import java.util.IdentityHashMap

internal const val COMPOSITION_CONTEXT = "compose.runtime.context"
private const val compositionLocalOfApi = "androidx.compose.runtime.compositionLocalOf"
private const val staticCompositionLocalOfApi = "androidx.compose.runtime.staticCompositionLocalOf"
private const val providesApi = "androidx.compose.runtime.ProvidableCompositionLocal.provides"
private const val providerApi = "androidx.compose.runtime.CompositionLocalProvider"
private val compositionContextSource = SourceSpan("EtsCompositionContext.kt", -1, -1)
internal val compositionLocalType = etsClassSymbol("EtsCompositionLocal", compositionContextSource).type as EtsNamedType
internal val compositionContextType = etsClassSymbol("EtsCompositionContext", compositionContextSource).type as EtsNamedType

internal fun compositionContext(scope: Scope, at: SourceSpan): EtsExpression = scope.ambientValues[COMPOSITION_CONTEXT]
    ?: throw Unsupported(Diagnostic("UNSUPPORTED", "CompositionLocal read requires a composition invocation context", at))

/** Resolves source CompositionLocal declarations to typed fields in one lexical target context. */
internal class ComposeCompositionLocalRule(private val diagnostics: DiagnosticSink) : CallRule {
    internal data class Definition(
        val declaration: IrDeclaration,
        val factory: IrCall,
        val defaultFactory: IrExpression,
        val valueType: IrType,
        var ordinal: Int = -1,
        var targetType: EtsType? = null,
    )

    private val definitionsByDeclaration = IdentityHashMap<IrDeclaration, Definition>()
    private val definitionsByFactory = IdentityHashMap<IrCall, Definition>()
    private val definitions = mutableListOf<Definition>()
    private val active = mutableListOf<Definition>()

    val contextRequired get() = active.isNotEmpty()

    override fun prepareModule(module: IrModuleFragment, diagnostics: DiagnosticSink) {
        definitionsByDeclaration.clear(); definitionsByFactory.clear(); definitions.clear(); active.clear()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitProperty(declaration: IrProperty) {
                declaration.backingField?.initializer?.expression?.let { initializer ->
                    factoryCall(initializer)?.let { register(declaration, it, declaration.backingField) }
                }
                declaration.acceptChildrenVoid(this)
            }
            override fun visitVariable(declaration: IrVariable) {
                declaration.initializer?.let { initializer ->
                    factoryCall(initializer)?.let { register(declaration, it) }
                }
                declaration.acceptChildrenVoid(this)
            }
        })
        definitions.sortWith(compareBy({ sourceFile(it.declaration)?.fileEntry?.name }, { it.declaration.startOffset }))
    }

    fun prepareForLowering(module: IrModuleFragment, language: Language) {
        active.clear()
        val uses = IdentityHashMap<Definition, IrExpression>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitCall(expression: IrCall) {
                val owner = expression.symbol.owner
                when {
                    isCompositionLocalCurrent(owner) -> definition(expression.dispatchReceiver, null)?.let {
                        uses.putIfAbsent(it, expression)
                    }
                    sourceFile(owner) == null && symbolName(owner) == providesApi ->
                        definition(expression.dispatchReceiver, null)?.let { uses.putIfAbsent(it, expression) }
                }
                expression.acceptChildrenVoid(this)
            }
        })
        definitions.filter { it in uses }.forEach { definition ->
            val use = uses.getValue(definition)
            definition.ordinal = active.size
            definition.targetType = try {
                language.type(definition.valueType)
            } catch (failure: Unsupported) {
                throw Unsupported(Diagnostic("UNSUPPORTED", failure.message ?: "Unsupported CompositionLocal value type",
                    language.source(use)))
            }
            active += definition
        }
    }

    override fun mapType(type: IrType, language: Language): EtsType? {
        val simple = type as? IrSimpleType ?: return null
        val owner = simple.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.runtime.CompositionLocal",
            "androidx.compose.runtime.ProvidableCompositionLocal" -> compositionLocalType
            "androidx.compose.runtime.ProvidedValue" -> {
                val projection = simple.arguments.singleOrNull() as? IrTypeProjection ?: return null
                EtsNamedType("EtsProvidedValue", listOf(language.type(projection.type)), external = true)
            }
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val api = symbolName(owner)
        val at = language.source(call)
        if (sourceFile(owner) == null && api in setOf(compositionLocalOfApi, staticCompositionLocalOfApi)) {
            validateFactory(call, language)
            return EtsNew(compositionLocalType, emptyList(), at)
        }
        if (isCompositionLocalCurrent(owner)) {
            val definition = definition(call.dispatchReceiver, scope) ?: return null
            val type = definition.targetType ?: diagnostics.unsupported(call,
                "CompositionLocal declaration is outside the resolved source module")
            if (!etsAssignable(type, language.type(call.type)) || !etsAssignable(language.type(call.type), type))
                diagnostics.unsupported(call, "CompositionLocal current type differs from its declaration")
            return current(definition, compositionContext(scope, at), at)
        }
        if (sourceFile(owner) == null && api == providesApi && definition(call.dispatchReceiver, scope) != null)
            diagnostics.unsupported(call, "CompositionLocal provides must be consumed by CompositionLocalProvider")
        return null
    }

    fun providedValue(call: IrCall, language: Language, scope: Scope): Pair<Definition, EtsExpression> {
        val owner = call.symbol.owner
        val at = language.source(call)
        if (sourceFile(owner) != null || symbolName(owner) != providesApi ||
            owner.valueParameters.map { it.name.asString() } != listOf("value") ||
            owner.extensionReceiverParameter != null || owner.dispatchReceiverParameter == null)
            diagnostics.unsupported(call, "Unsupported CompositionLocal provides signature")
        val receiver = call.dispatchReceiver ?: diagnostics.unsupported(call, "CompositionLocal provides requires receiver")
        val definition = definition(receiver, scope)
            ?: diagnostics.unsupported(receiver, "CompositionLocal provider receiver must resolve to a source declaration")
        val value = argument(call, "value") ?: diagnostics.unsupported(call, "CompositionLocal provides requires value")
        val lowered = language.expression(value, scope)
        val expected = definition.targetType ?: diagnostics.unsupported(call,
            "CompositionLocal declaration is outside the resolved source module")
        if (!etsAssignable(lowered.type, expected)) diagnostics.unsupported(value,
            "CompositionLocal provided value has target type ${lowered.type}; expected $expected")
        return definition to lowered
    }

    fun defaultContext(language: Language, scope: Scope, at: SourceSpan): EtsExpression {
        val factories = active.map { definition ->
            val lowered = language.expression(definition.defaultFactory, scope)
            val expected = fieldType(definition)
            if (lowered.type != expected) throw Unsupported(Diagnostic("UNSUPPORTED",
                "CompositionLocal default factory has target type ${lowered.type}; expected $expected",
                language.source(definition.defaultFactory)))
            lowered
        }
        return EtsNew(compositionContextType, factories, at)
    }

    fun overriddenContext(parent: EtsExpression, values: Map<Definition, EtsExpression>, at: SourceSpan): EtsExpression =
        EtsNew(compositionContextType, active.map { definition ->
            values[definition]?.let { value ->
                EtsLambda(emptyList(), listOf(EtsReturn(value, at)), definition.targetType!!, at)
            } ?: EtsMember(parent, fieldName(definition), fieldType(definition), at, fieldSymbol(definition).id)
        }, at)

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var markerUsed = false
        var contextUsed = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> {
                    if (value.symbolId == compositionLocalType.symbolId) markerUsed = true
                    if (value.symbolId == compositionContextType.symbolId) contextUsed = true
                    value.arguments.forEach(::type)
                }
                is EtsNullableType -> type(value.inner)
                is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
                is EtsTupleType -> value.elements.forEach(::type)
                is EtsRecordType -> value.fields.values.forEach(::type)
                is EtsCapturedType -> { type(value.readType); type(value.writeType) }
                is EtsTypeParameterType -> Unit
            }
        }
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsExpression) type(node.type)
            when (node) {
                is EtsFunction -> type(node.symbol.type)
                is EtsField -> type(node.symbol.type)
                is EtsGlobal -> type(node.symbol.type)
                is EtsVariable -> type(node.symbol.type)
                else -> Unit
            }
        } } }
        if (!markerUsed && !contextUsed) return emptyList()
        val declarations = mutableListOf<EtsDeclaration>()
        if (markerUsed) declarations += EtsClass(compositionLocalType.name, listOf(EtsFunction("constructor",
            emptyList(), EtsTypes.VOID, emptyList(), compositionContextSource, kind = EtsFunctionKind.CONSTRUCTOR)),
            compositionContextSource, exported = true)
        if (contextUsed) declarations += contextClass()
        return listOf(EtsFile(compositionContextSource.file!!, declarations))
    }

    private fun register(declaration: IrDeclaration, factory: IrCall, field: IrField? = null) {
        if (declaration in definitionsByDeclaration) return
        val default = argument(factory, "defaultFactory") ?: diagnostics.unsupported(factory,
            "CompositionLocal declaration requires a default factory")
        val simple = factory.type as? IrSimpleType
            ?: diagnostics.unsupported(factory, "CompositionLocal declaration requires a concrete value type")
        val projection = simple.arguments.singleOrNull() as? IrTypeProjection
            ?: diagnostics.unsupported(factory, "CompositionLocal declaration requires one invariant value type")
        val definition = Definition(declaration, factory, default, projection.type)
        definitions += definition
        definitionsByDeclaration[declaration] = definition
        field?.let { definitionsByDeclaration[it] = definition }
        definitionsByFactory[factory] = definition
    }

    private fun validateFactory(call: IrCall, language: Language) {
        val owner = call.symbol.owner
        val names = owner.valueParameters.map { it.name.asString() }
        val valid = when (symbolName(owner)) {
            compositionLocalOfApi -> names == listOf("policy", "defaultFactory") &&
                call.getValueArgument(names.indexOf("policy")) == null
            staticCompositionLocalOfApi -> names == listOf("defaultFactory")
            else -> false
        }
        if (!valid || owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null ||
            owner.typeParameters.size != 1 || call.type.classOrNull?.owner?.let(::symbolName) !=
                "androidx.compose.runtime.ProvidableCompositionLocal")
            diagnostics.unsupported(call, "Unsupported CompositionLocal factory signature")
        argument(call, "defaultFactory") ?: diagnostics.unsupported(call, "CompositionLocal factory requires defaultFactory")
    }

    private fun factoryCall(expression: IrExpression?): IrCall? = when (expression) {
        is IrCall -> expression.takeIf { sourceFile(it.symbol.owner) == null &&
            symbolName(it.symbol.owner) in setOf(compositionLocalOfApi, staticCompositionLocalOfApi) }
        is IrTypeOperatorCall -> factoryCall(expression.argument)
        is IrBlock -> factoryCall(expression.statements.lastOrNull() as? IrExpression)
        else -> null
    }

    fun definition(expression: IrExpression?, scope: Scope?): Definition? = when (expression) {
        is IrGetValue -> definitionsByDeclaration[expression.symbol.owner as? IrDeclaration]
            ?: scope?.aliases?.get(expression.symbol)?.let { definition(it, scope) }
            ?: (expression.symbol.owner as? IrVariable)?.takeUnless { it.isVar }?.initializer?.let { definition(it, scope) }
        is IrGetField -> definitionsByDeclaration[expression.symbol.owner]
            ?: expression.symbol.owner.correspondingPropertySymbol?.owner?.let { definitionsByDeclaration[it] }
            ?: expression.symbol.owner.initializer?.expression?.let { definition(it, scope) }
        is IrCall -> expression.symbol.owner.correspondingPropertySymbol?.owner?.let { definitionsByDeclaration[it] }
            ?: definitionsByFactory[expression]
        is IrTypeOperatorCall -> definition(expression.argument, scope)
        is IrBlock -> definition(expression.statements.lastOrNull() as? IrExpression, scope)
        else -> null
    }

    private fun fieldName(definition: Definition) = "local${definition.ordinal}"
    private fun fieldType(definition: Definition) = EtsFunctionType(emptyList(), requireNotNull(definition.targetType))
    private fun fieldSymbol(definition: Definition) = EtsSymbol("compose:context:field:${definition.ordinal}",
        fieldName(definition), fieldType(definition), compositionContextSource)

    private fun current(definition: Definition, context: EtsExpression, at: SourceSpan): EtsExpression {
        val factory = EtsMember(context, fieldName(definition), fieldType(definition), at, fieldSymbol(definition).id)
        return EtsCall(factory, emptyList(), requireNotNull(definition.targetType), at)
    }

    private fun contextClass(): EtsClass {
        val self = EtsReference(EtsSymbol("target:compositionContext:this", "this", compositionContextType,
            compositionContextSource, external = true))
        val fields = active.map { EtsField(fieldSymbol(it), readonly = true) }
        val parameters = active.map { definition -> EtsParameter(EtsSymbol("compose:context:parameter:${definition.ordinal}",
            fieldName(definition), fieldType(definition), compositionContextSource)) }
        val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID,
            fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
                EtsMember(self, field.symbol.name, field.symbol.type, compositionContextSource, field.symbol.id),
                EtsReference(parameter.symbol), compositionContextSource)) }, compositionContextSource,
            kind = EtsFunctionKind.CONSTRUCTOR)
        return EtsClass(compositionContextType.name, fields + constructor, compositionContextSource,
            exported = true, valueSnapshot = true)
    }
}

/** Consumes provider varargs and enters content with a child typed lexical context. */
internal class ComposeCompositionLocalProviderRule(
    private val locals: ComposeCompositionLocalRule,
    private val diagnostics: DiagnosticSink,
    private val provide: (List<Pair<ComposeCompositionLocalRule.Definition, EtsExpression>>,
        IrExpression, Scope) -> List<EtsStatement>,
) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null

    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null || symbolName(owner) != providerApi) return null
        val names = owner.valueParameters.map { it.name.asString() }
        if (names !in setOf(listOf("values", "content"), listOf("value", "content")) ||
            owner.dispatchReceiverParameter != null || owner.extensionReceiverParameter != null || !owner.returnType.isUnit())
            diagnostics.unsupported(call, "Unsupported CompositionLocalProvider signature")
        val supplied = argument(call, names.first())
            ?: diagnostics.unsupported(call, "CompositionLocalProvider requires provided values")
        val expressions = when (supplied) {
            is IrVararg -> supplied.elements.map { element ->
                element as? IrExpression ?: diagnostics.unsupported(element, "Spread CompositionLocal providers are unsupported")
            }
            else -> listOf(supplied)
        }
        val content = argument(call, "content") ?: diagnostics.unsupported(call, "CompositionLocalProvider requires content")
        val values = expressions.map { expression ->
            val provided = expression as? IrCall
                ?: diagnostics.unsupported(expression, "CompositionLocalProvider values must be direct provides calls")
            locals.providedValue(provided, language, scope)
        }
        return provide(values, content, scope)
    }
}
