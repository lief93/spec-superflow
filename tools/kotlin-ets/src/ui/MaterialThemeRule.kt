@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.visitors.*

internal const val MATERIAL_CONTEXT = "compose.material3.context"
private val materialContextSource = SourceSpan("EtsMaterialContext.kt", -1, -1)
internal val materialContextType = etsClassSymbol("EtsMaterialContext", materialContextSource).type as EtsNamedType
private val materialThemeType = etsClassSymbol("EtsMaterialTheme", materialContextSource).type as EtsNamedType
private val materialThemeObject = EtsSymbol("material:theme:singleton", "__etsMaterialTheme", materialThemeType, materialContextSource)

internal fun materialContext(scope: Scope, at: SourceSpan): EtsExpression = scope.ambientValues[MATERIAL_CONTEXT]
    ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Material theme read requires a composition invocation context", at))
internal fun materialScheme(context: EtsExpression, at: SourceSpan) = EtsMember(context, "colorScheme", materialColorSchemeType, at)
internal fun materialContentColor(context: EtsExpression, at: SourceSpan) = EtsMember(context, "contentColor", EtsTypes.NUMBER, at)
internal fun defaultMaterialContext(at: SourceSpan): EtsExpression = EtsNew(materialContextType, listOf(
    EtsNew(materialColorSchemeType, materialColorSchemeDefaults.map { (name, defaults) ->
        if (name == "surfaceTint") EtsLiteral(null, EtsTypes.NULL, at) else EtsLiteral(defaults.first, EtsTypes.NUMBER, at)
    }, at), EtsLiteral(0xFF000000L, EtsTypes.NUMBER, at), defaultTypography(at)), at)

internal fun requiresMaterialContext(element: IrElement): Boolean {
    var required = false
    element.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
        override fun visitCall(expression: IrCall) {
            val owner = expression.symbol.owner
            val api = symbolName(owner)
            if (sourceFile(owner) == null && (api == "androidx.compose.material3.MaterialTheme" ||
                api in setOf("androidx.compose.material3.Button", "androidx.compose.material3.TextButton",
                    "androidx.compose.material3.ButtonDefaults.buttonColors", "androidx.compose.material3.ButtonDefaults.textButtonColors") ||
                owner.correspondingPropertySymbol?.owner?.let(::symbolName) in setOf("androidx.compose.material3.MaterialTheme.colorScheme", "androidx.compose.material3.MaterialTheme.typography") ||
                api == "androidx.compose.material3.contentColorFor" ||
                api == "androidx.compose.material3.Surface" &&
                (argument(expression, "color") == null || argument(expression, "contentColor") == null))) required = true
            expression.acceptChildrenVoid(this)
        }
    })
    return required
}

// AndroidX ColorScheme.contentColorFor order matters when roles have equal colors.
private val contentRoles = linkedMapOf("primary" to "onPrimary", "secondary" to "onSecondary",
    "tertiary" to "onTertiary", "background" to "onBackground", "error" to "onError",
    "primaryContainer" to "onPrimaryContainer", "secondaryContainer" to "onSecondaryContainer",
    "tertiaryContainer" to "onTertiaryContainer", "errorContainer" to "onErrorContainer",
    "inverseSurface" to "inverseOnSurface", "surface" to "onSurface", "surfaceVariant" to "onSurfaceVariant",
    "surfaceBright" to "onSurface", "surfaceContainer" to "onSurface", "surfaceContainerHigh" to "onSurface",
    "surfaceContainerHighest" to "onSurface", "surfaceContainerLow" to "onSurface", "surfaceContainerLowest" to "onSurface")

internal fun materialContentColorFor(context: EtsExpression, background: EtsExpression, at: SourceSpan): EtsExpression =
    EtsCall(EtsMember(context, "contentColorFor", EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.NUMBER), at),
        listOf(background), EtsTypes.NUMBER, at)

internal class ComposeMaterialThemeValueRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        if (sourceFile(it) == null && symbolName(it) == "androidx.compose.material3.MaterialTheme") materialThemeType else null
    }
    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? =
        if (sourceFile(value.symbol.owner) == null && symbolName(value.symbol.owner) == "androidx.compose.material3.MaterialTheme")
            EtsReference(materialThemeObject, language.source(value)) else null
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (property in setOf("androidx.compose.material3.MaterialTheme.colorScheme", "androidx.compose.material3.MaterialTheme.typography")) {
            if (call.dispatchReceiver !is IrGetObjectValue && call.dispatchReceiver !is IrGetValue)
                throw Unsupported(Diagnostic("UNSUPPORTED", "Bind MaterialTheme receiver to a source variable before reading theme properties", at))
            // The singleton is not a snapshot: getters read the invocation's CompositionLocal.
            return if (property!!.endsWith(".colorScheme")) materialScheme(materialContext(scope, at), at)
                else materialTypography(materialContext(scope, at), at)
        }
        if (symbolName(owner) == "androidx.compose.material3.contentColorFor") {
            if (owner.extensionReceiverParameter != null || owner.dispatchReceiverParameter != null)
                throw Unsupported(Diagnostic("UNSUPPORTED", "ColorScheme.contentColorFor requires explicit receiver and Unspecified result semantics", at))
            val background = argument(call, "backgroundColor") ?: return null
            return materialContentColorFor(materialContext(scope, at), language.expression(background, scope), at)
        }
        return null
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var used = false
        var singleton = false
        fun type(value: EtsType) {
            when (value) {
                is EtsNamedType -> { if (value.symbolId == materialThemeType.symbolId) singleton = true; value.arguments.forEach(::type) }
                is EtsNullableType -> type(value.inner)
                is EtsFunctionType -> { value.parameters.forEach(::type); type(value.result) }
                is EtsRecordType -> value.fields.values.forEach(::type)
                is EtsTupleType -> value.elements.forEach(::type)
                is EtsCapturedType -> { type(value.readType); type(value.writeType) }
                is EtsTypeParameterType -> Unit
            }
        }
        program.files.forEach { it.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsNew && it.classType == materialContextType) used = true
            if (it is EtsExpression) type(it.type)
            when (it) {
                is EtsFunction -> type(it.symbol.type)
                is EtsField -> type(it.symbol.type)
                is EtsGlobal -> type(it.symbol.type)
                is EtsVariable -> type(it.symbol.type)
                else -> Unit
            }
        } } }
        val marker = if (singleton) listOf(EtsClass(materialThemeType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
            emptyList(), materialContextSource, kind = EtsFunctionKind.CONSTRUCTOR)), materialContextSource, exported = true),
            EtsGlobal(materialThemeObject, EtsNew(materialThemeType, emptyList(), materialContextSource), false, exported = true)) else emptyList()
        if (!used) return if (marker.isEmpty()) emptyList() else listOf(EtsFile(materialContextSource.file!!, marker))
        val at = materialContextSource
        val self = EtsReference(EtsSymbol("material:context:this", "this", materialContextType, at, external = true))
        val values = linkedMapOf("colorScheme" to materialColorSchemeType, "contentColor" to EtsTypes.NUMBER, "typography" to typographyType)
        val parameters = values.map { (name, type) -> EtsParameter(EtsSymbol("material:context:parameter:$name", name, type, at)) }
        val fields = values.map { (name, type) -> EtsField(EtsSymbol("material:context:field:$name", name, type, at), readonly = true) }
        val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, fields.zip(parameters).map { (field, parameter) ->
            EtsExpressionStatement(EtsAssignment(EtsMember(self, field.symbol.name, field.symbol.type, at, field.symbol.id),
                EtsReference(parameter.symbol), at))
        }, at, kind = EtsFunctionKind.CONSTRUCTOR)
        val background = EtsParameter(EtsSymbol("material:context:background", "background", EtsTypes.NUMBER, at))
        val scheme = materialScheme(self, at)
        val match = contentRoles.entries.toList().asReversed().fold(materialContentColor(self, at) as EtsExpression) { fallback, (role, onRole) ->
            EtsConditional(EtsBinary("===", EtsReference(background.symbol), EtsMember(scheme, role, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
                EtsMember(scheme, onRole, EtsTypes.NUMBER, at), fallback, EtsTypes.NUMBER, at)
        }
        val method = EtsFunction("contentColorFor", listOf(background), EtsTypes.NUMBER, listOf(EtsReturn(match, at)), at, kind = EtsFunctionKind.METHOD)
        return listOf(EtsFile(at.file!!, marker + EtsClass(materialContextType.name, fields + constructor + method, at, exported = true)))
    }
}

internal class ComposeMaterialThemeRule(private val target: ArkUiCalls,
    private val provide: (EtsExpression, IrExpression, Scope) -> List<EtsStatement>) : CallRule {
    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
    override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
        if (symbolName(call.symbol.owner) != "androidx.compose.material3.MaterialTheme") return null
        target.checkArguments(call, setOf("colorScheme", "typography", "content"))
        val at = language.source(call)
        val parent = materialContext(scope, at)
        val scheme = argument(call, "colorScheme")?.let { language.expression(it, scope) } ?: materialScheme(parent, at)
        val typography = argument(call, "typography")?.let { language.expression(it, scope) } ?: materialTypography(parent, at)
        val content = argument(call, "content") ?: target.diagnostics.unsupported(call, "MaterialTheme requires content")
        return provide(EtsNew(materialContextType, listOf(scheme, materialContentColor(parent, at), typography), at), content, scope)
    }
}
