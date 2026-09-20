@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.types.isInt
import org.jetbrains.kotlin.ir.types.isString

private val toastSource = SourceSpan("EtsToast.kt", -1, -1)
private val toastOptionsType = EtsRecordType("ShowToastOptions", mapOf(
    "message" to EtsTypes.STRING, "duration" to EtsTypes.NUMBER))
private val promptActionType = EtsNamedType("promptAction", external = true)
private val promptActionSymbol = EtsSymbol("arkui:promptAction", "promptAction", promptActionType, toastSource, true)
private val showToastType = EtsFunctionType(listOf(toastOptionsType), EtsTypes.VOID)

/**
 * Toast.makeText(...).show() is host promptAction.showToast. LENGTH_SHORT/LONG are Android's
 * documented 2000/3500ms delays, not invented host defaults. Other Toast APIs remain unsupported.
 */
internal class ComposeToastRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        if (sourceFile(it) == null && symbolName(it) == "android.widget.Toast") toastOptionsType else null
    }

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        val name = value.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: symbolName(value.symbol.owner)
        val duration = when (name) {
            "android.widget.Toast.LENGTH_SHORT" -> 2000
            "android.widget.Toast.LENGTH_LONG" -> 3500
            else -> return null
        }
        return EtsLiteral(duration, EtsTypes.NUMBER, language.source(value))
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        val api = symbolName(owner)
        if (api == "android.widget.Toast.makeText") {
            if (call.valueArgumentsCount != 3) return null
            val context = call.getValueArgument(0) ?: return null
            val text = call.getValueArgument(1) ?: return null
            val duration = call.getValueArgument(2) ?: return null
            if (!text.type.isString()) throw Unsupported(Diagnostic("UNSUPPORTED",
                "Toast.makeText currently requires a String message", language.source(text)))
            if (!duration.type.isInt()) throw Unsupported(Diagnostic("UNSUPPORTED",
                "Toast.makeText currently requires LENGTH_SHORT or LENGTH_LONG", language.source(duration)))
            language.expression(context, scope)
            val delay = when (val value = language.expression(duration, scope)) {
                is EtsLiteral -> when (value.value) {
                    0, 2000 -> EtsLiteral(2000, EtsTypes.NUMBER, value.source)
                    1, 3500 -> EtsLiteral(3500, EtsTypes.NUMBER, value.source)
                    else -> throw Unsupported(Diagnostic("UNSUPPORTED",
                        "Toast.makeText currently requires LENGTH_SHORT or LENGTH_LONG", value.source))
                }
                else -> value
            }
            return EtsObject(linkedMapOf(
                "message" to language.expression(text, scope),
                "duration" to delay), toastOptionsType, at)
        }
        if (api == "android.widget.Toast.show") {
            val receiver = call.dispatchReceiver ?: return null
            val options = language.expression(receiver, scope)
            return EtsCall(EtsMember(EtsReference(promptActionSymbol, at), "showToast", showToastType, at),
                listOf(options), EtsTypes.VOID, at)
        }
        return null
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id == promptActionSymbol.id) used = true
        } } }
        return if (used) listOf(EtsImport("@kit.ArkUI", "promptAction")) else emptyList()
    }
}
