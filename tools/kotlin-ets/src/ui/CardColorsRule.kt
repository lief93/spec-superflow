@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val cardColorFields = listOf(
    "containerColor", "contentColor", "disabledContainerColor", "disabledContentColor")
private val cardColorsSource = SourceSpan("EtsCardColors.kt", -1, -1)
internal val cardColorsType = etsClassSymbol("EtsCardColors", cardColorsSource).type as EtsNamedType

/** Converts Material CardColors into a typed target value consumed by the Card backend. */
internal class ComposeCardColorsRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        return cardColorsType.takeIf {
            sourceFile(owner) == null && symbolName(owner) == "androidx.compose.material3.CardColors"
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val api = symbolName(owner)
        val at = language.source(call)
        if (sourceFile(owner) == null && api == "androidx.compose.material3.CardDefaults.cardColors") {
            val scheme = materialScheme(materialContext(scope, at), at)
            fun role(name: String) = EtsMember(scheme, name, EtsTypes.NUMBER, at)
            val defaults = linkedMapOf(
                "containerColor" to role("surfaceContainerHighest"),
                "contentColor" to role("onSurface"),
                "disabledContainerColor" to role("surfaceContainerHighest"),
                "disabledContentColor" to role("onSurface"),
            )
            return EtsNew(cardColorsType, cardColorFields.map { name ->
                val fallback = defaults.getValue(name)
                argument(call, name)?.let { value ->
                    resolveComposeColor(language.expression(value, scope), fallback, language.source(value))
                } ?: fallback
            }, at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol ||
            symbolName(property.parent as? IrClass ?: return null) != "androidx.compose.material3.CardColors" ||
            property.name.asString() !in cardColorFields) return null
        return EtsMember(language.expression(call.dispatchReceiver!!, scope), property.name.asString(), EtsTypes.NUMBER, at)
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        var required = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            fun uses(type: EtsType): Boolean = when (type) {
                is EtsNamedType -> type == cardColorsType || type.arguments.any(::uses)
                is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
                is EtsNullableType -> uses(type.inner)
                else -> false
            }
            if (node is EtsExpression && uses(node.type)) required = true
            if (node is EtsFunction && uses(node.symbol.type)) required = true
            if (node is EtsField && uses(node.symbol.type)) required = true
        } } }
        if (!required) return emptyList()
        val self = EtsReference(EtsSymbol("card:colors:this", "this", cardColorsType, cardColorsSource, true))
        val fields = cardColorFields.map {
            EtsField(EtsSymbol("card:colors:$it", it, EtsTypes.NUMBER, cardColorsSource), readonly = true)
        }
        val parameters = fields.map { EtsParameter(it.symbol.copy(id = it.symbol.id + ":parameter")) }
        val body = fields.zip(parameters).map { (field, parameter) -> EtsExpressionStatement(EtsAssignment(
            EtsMember(self, field.symbol.name, field.symbol.type, cardColorsSource, field.symbol.id),
            EtsReference(parameter.symbol), cardColorsSource)) }
        val declaration = EtsClass(cardColorsType.name, fields + EtsFunction("constructor", parameters, EtsTypes.VOID,
            body, cardColorsSource, kind = EtsFunctionKind.CONSTRUCTOR), cardColorsSource,
            exported = true, valueSnapshot = true)
        return listOf(EtsFile(cardColorsSource.file!!, listOf(declaration)))
    }
}
