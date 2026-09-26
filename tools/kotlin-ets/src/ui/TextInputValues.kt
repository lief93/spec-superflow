@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val inputSource = SourceSpan("EtsTextInputValues.kt", -1, -1)
internal val visualTransformationType = etsClassSymbol("EtsVisualTransformation", inputSource).type as EtsNamedType
internal val keyboardOptionsType = etsClassSymbol("EtsKeyboardOptions", inputSource).type as EtsNamedType
internal val keyboardActionsType = etsClassSymbol("EtsKeyboardActions", inputSource).type as EtsNamedType
internal val interactionSourceType = etsClassSymbol("EtsMutableInteractionSource", inputSource).type as EtsNamedType
internal val textFieldColorsType = etsClassSymbol("EtsTextFieldColors", inputSource).type as EtsNamedType
private val textFieldDefaultsType = etsClassSymbol("EtsTextFieldDefaults", inputSource).type as EtsNamedType
private val textFieldDefaultsObject = EtsSymbol("compose:textFieldDefaults", "__etsTextFieldDefaults",
    textFieldDefaultsType, inputSource)
private val noneTransformation = EtsSymbol("compose:visualTransformationNone", "__etsVisualTransformationNone",
    visualTransformationType, inputSource)
private val passwordTransformation = EtsSymbol("compose:visualTransformationPassword", "__etsVisualTransformationPassword",
    visualTransformationType, inputSource)
private val defaultKeyboardOptions = EtsSymbol("compose:keyboardOptionsDefault", "__etsKeyboardOptionsDefault",
    keyboardOptionsType, inputSource)
private val defaultKeyboardActions = EtsSymbol("compose:keyboardActionsDefault", "__etsKeyboardActionsDefault",
    keyboardActionsType, inputSource)
private val visualTransformationCompanionType = etsClassSymbol("EtsVisualTransformationCompanion", inputSource).type as EtsNamedType
private val keyboardOptionsCompanionType = etsClassSymbol("EtsKeyboardOptionsCompanion", inputSource).type as EtsNamedType
private val keyboardActionsCompanionType = etsClassSymbol("EtsKeyboardActionsCompanion", inputSource).type as EtsNamedType
private val visualTransformationCompanion = EtsSymbol("compose:visualTransformationCompanion",
    "__etsVisualTransformationCompanion", visualTransformationCompanionType, inputSource)
private val keyboardOptionsCompanion = EtsSymbol("compose:keyboardOptionsCompanion",
    "__etsKeyboardOptionsCompanion", keyboardOptionsCompanionType, inputSource)
private val keyboardActionsCompanion = EtsSymbol("compose:keyboardActionsCompanion",
    "__etsKeyboardActionsCompanion", keyboardActionsCompanionType, inputSource)

internal fun isPasswordTransformation(value: EtsExpression): EtsExpression {
    val at = value.source
    return EtsBinary("===", value, EtsReference(passwordTransformation, at), EtsTypes.BOOLEAN, at)
}

/** Typed host values for BasicTextField defaults; live IME/indication behavior is not implied. */
internal class ComposeTextInputValueRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null) return null
        return when (symbolName(owner)) {
            "androidx.compose.ui.text.input.VisualTransformation",
            "androidx.compose.ui.text.input.PasswordVisualTransformation" -> visualTransformationType
            "androidx.compose.foundation.text.KeyboardOptions" -> keyboardOptionsType
            "androidx.compose.foundation.text.KeyboardActions" -> keyboardActionsType
            "androidx.compose.foundation.interaction.MutableInteractionSource",
            "androidx.compose.foundation.interaction.InteractionSource" -> interactionSourceType
            "androidx.compose.material3.TextFieldColors" -> textFieldColorsType
            "androidx.compose.material3.TextFieldDefaults",
            "androidx.compose.material3.OutlinedTextFieldDefaults" -> textFieldDefaultsType
            "androidx.compose.ui.text.input.VisualTransformation.Companion" -> visualTransformationCompanionType
            "androidx.compose.foundation.text.KeyboardOptions.Companion" -> keyboardOptionsCompanionType
            "androidx.compose.foundation.text.KeyboardActions.Companion" -> keyboardActionsCompanionType
            else -> null
        }
    }

    override fun lowerObject(value: IrGetObjectValue, language: Language, scope: Scope): EtsExpression? {
        if (sourceFile(value.symbol.owner) != null) return null
        val at = language.source(value)
        return when (symbolName(value.symbol.owner)) {
            "androidx.compose.material3.TextFieldDefaults",
            "androidx.compose.material3.OutlinedTextFieldDefaults" -> EtsReference(textFieldDefaultsObject, at)
            "androidx.compose.ui.text.input.VisualTransformation.Companion" -> EtsReference(visualTransformationCompanion, at)
            "androidx.compose.foundation.text.KeyboardOptions.Companion" -> EtsReference(keyboardOptionsCompanion, at)
            "androidx.compose.foundation.text.KeyboardActions.Companion" -> EtsReference(keyboardActionsCompanion, at)
            else -> null
        }
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner.parent as? IrClass ?: return null
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        (0 until call.valueArgumentsCount).forEach { index ->
            call.getValueArgument(index)?.let { language.expression(it, scope) }
        }
        return when (symbolName(owner)) {
            "androidx.compose.ui.text.input.PasswordVisualTransformation" -> EtsReference(passwordTransformation, at)
            "androidx.compose.foundation.text.KeyboardOptions" -> EtsReference(defaultKeyboardOptions, at)
            "androidx.compose.foundation.text.KeyboardActions" -> EtsReference(defaultKeyboardActions, at)
            "androidx.compose.foundation.interaction.MutableInteractionSource" -> EtsNew(interactionSourceType, emptyList(), at)
            "androidx.compose.material3.TextFieldColors" -> EtsNew(textFieldColorsType, emptyList(), at)
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val at = language.source(call)
        val api = symbolName(owner)
        if (api in setOf("androidx.compose.runtime.remember", "androidx.compose.runtime.saveable.rememberSaveable")) {
            val calculation = argument(call, "calculation") ?: argument(call, "init") ?: return null
            val result = rememberedValue(calculation, scope) ?: return null
            val function = when (result) {
                is IrConstructorCall -> result.symbol.owner
                is IrCall -> result.symbol.owner
                else -> return null
            }
            val parent = function.parent as? IrClass
            val name = symbolName(function)
            val parentName = parent?.let(::symbolName)
            if (name != "androidx.compose.foundation.interaction.MutableInteractionSource" &&
                parentName != "androidx.compose.foundation.interaction.MutableInteractionSource") return null
            (0 until result.valueArgumentsCount).forEach { index ->
                result.getValueArgument(index)?.let { language.expression(it, scope) }
            }
            return EtsNew(interactionSourceType, emptyList(), at, stableIdentity = true)
        }
        if (api == "androidx.compose.foundation.interaction.MutableInteractionSource") {
            (0 until call.valueArgumentsCount).forEach { index ->
                call.getValueArgument(index)?.let { language.expression(it, scope) }
            }
            return EtsNew(interactionSourceType, emptyList(), at)
        }
        if (api == "androidx.compose.ui.text.input.PasswordVisualTransformation") {
            (0 until call.valueArgumentsCount).forEach { index ->
                call.getValueArgument(index)?.let { language.expression(it, scope) }
            }
            return EtsReference(passwordTransformation, at)
        }
        if (api in setOf("androidx.compose.material3.TextFieldDefaults.colors",
                "androidx.compose.material3.OutlinedTextFieldDefaults.colors")) {
            val receiver = call.dispatchReceiver
            if (receiver !is IrGetObjectValue && receiver !is IrGetValue)
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "Bind TextFieldDefaults receiver to a source variable before calling its color factory", at))
            (0 until call.valueArgumentsCount).forEach { index ->
                call.getValueArgument(index)?.let { language.expression(it, scope) }
            }
            return EtsNew(textFieldColorsType, emptyList(), at)
        }
        val property = owner.correspondingPropertySymbol?.owner ?: return null
        if (property.getter?.symbol != owner.symbol) return null
        return when (symbolName(property)) {
            "androidx.compose.ui.text.input.VisualTransformation.Companion.None",
            "androidx.compose.ui.text.input.VisualTransformation.None" -> EtsReference(noneTransformation, at)
            "androidx.compose.foundation.text.KeyboardOptions.Companion.Default",
            "androidx.compose.foundation.text.KeyboardOptions.Default" -> EtsReference(defaultKeyboardOptions, at)
            "androidx.compose.foundation.text.KeyboardActions.Companion.Default",
            "androidx.compose.foundation.text.KeyboardActions.Default" -> EtsReference(defaultKeyboardActions, at)
            else -> null
        }
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        val used = mutableSetOf<EtsNamedType>()
        fun uses(type: EtsType) {
            when (type) {
                is EtsNamedType -> {
                    if (type.symbolId in setOf(visualTransformationType.symbolId, keyboardOptionsType.symbolId,
                            keyboardActionsType.symbolId, interactionSourceType.symbolId, textFieldColorsType.symbolId,
                            textFieldDefaultsType.symbolId, visualTransformationCompanionType.symbolId,
                            keyboardOptionsCompanionType.symbolId, keyboardActionsCompanionType.symbolId)) used += type
                    type.arguments.forEach(::uses)
                }
                is EtsFunctionType -> { type.parameters.forEach(::uses); uses(type.result) }
                is EtsNullableType -> uses(type.inner)
                else -> Unit
            }
        }
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsExpression) uses(node.type)
            if (node is EtsFunction) uses(node.symbol.type)
            if (node is EtsField) uses(node.symbol.type)
        } } }
        if (used.isEmpty()) return emptyList()
        val declarations = mutableListOf<EtsDeclaration>()
        fun marker(type: EtsNamedType, global: EtsSymbol? = null, valueSnapshot: Boolean = false) {
            if (used.none { it.symbolId == type.symbolId }) return
            declarations += EtsClass(type.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
                emptyList(), inputSource, kind = EtsFunctionKind.CONSTRUCTOR)), inputSource, exported = true,
                valueSnapshot = valueSnapshot)
            if (global != null) declarations += EtsGlobal(global, EtsNew(type, emptyList(), inputSource), false, exported = true)
        }
        marker(visualTransformationType)
        if (used.any { it.symbolId == visualTransformationType.symbolId }) {
            declarations += EtsGlobal(noneTransformation, EtsNew(visualTransformationType, emptyList(), inputSource), false, exported = true)
            declarations += EtsGlobal(passwordTransformation, EtsNew(visualTransformationType, emptyList(), inputSource), false, exported = true)
        }
        marker(visualTransformationCompanionType, visualTransformationCompanion)
        marker(keyboardOptionsType, defaultKeyboardOptions)
        marker(keyboardOptionsCompanionType, keyboardOptionsCompanion)
        marker(keyboardActionsType, defaultKeyboardActions)
        marker(keyboardActionsCompanionType, keyboardActionsCompanion)
        marker(interactionSourceType)
        marker(textFieldColorsType, valueSnapshot = true)
        marker(textFieldDefaultsType, textFieldDefaultsObject)
        return listOf(EtsFile(inputSource.file!!, declarations))
    }

    private fun rememberedValue(expression: IrExpression, scope: Scope): IrFunctionAccessExpression? {
        val fn = lambda(expression, scope) ?: return null
        val statements = (fn.body as? IrBlockBody)?.statements ?: (fn.body as? IrExpressionBody)?.let { listOf(it.expression) }
            ?: return null
        val result = statements.singleOrNull() ?: return null
        val value = (result as? IrReturn)?.value ?: result as? IrExpression ?: return null
        return resolveExpression(value, scope) as? IrFunctionAccessExpression
    }
}
