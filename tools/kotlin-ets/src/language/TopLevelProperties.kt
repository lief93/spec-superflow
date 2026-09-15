@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*

private fun propertySource(property: IrProperty) =
    SourceSpan(sourceFile(property)?.fileEntry?.name, property.startOffset, property.endOffset)

private fun rejectProperty(property: IrProperty, message: String): Nothing =
    throw Unsupported(Diagnostic("UNSUPPORTED", message, propertySource(property)))

internal fun topLevelStorage(property: IrProperty, language: Language): EtsSymbol {
    if (property.parent !is IrFile || sourceFile(property) == null || property.isExternal || property.isExpect ||
        property.isDelegated || property.isLateinit ||
        listOfNotNull(property.getter, property.setter).any { it.extensionReceiverParameter != null ||
            it.dispatchReceiverParameter != null || it.typeParameters.isNotEmpty() ||
            it.origin != IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR }) {
        rejectProperty(property, "Top-level properties require ordinary source storage and default accessors")
    }
    val field = property.backingField ?: rejectProperty(property, "Top-level property has no backing storage")
    if (field.initializer?.expression !is IrConst) rejectProperty(property,
        "Top-level property initializer requires file-initialization lowering; only constant initial values are supported")
    val at = propertySource(property)
    val name = property.name.asString()
    return EtsSymbol("global:${at.file}:${at.start}:$name", name, language.type(field.type), at)
}

private fun exportedSetter(property: IrProperty): Boolean = property.setter?.let {
    !DescriptorVisibilities.isPrivate(property.visibility) && !DescriptorVisibilities.isPrivate(it.visibility)
} == true

private fun setterFunction(storage: EtsSymbol): EtsFunction {
    val at = storage.source
    val parameter = EtsSymbol("${storage.id}:value", if (storage.name == "value") "newValue" else "value", storage.type, at)
    return EtsFunction("__etsSet_${storage.name}", listOf(EtsParameter(parameter)), EtsTypes.VOID,
        listOf(EtsExpressionStatement(EtsAssignment(EtsReference(storage), EtsReference(parameter), at))),
        at, exported = true)
}

internal fun lowerTopLevelProperty(property: IrProperty, language: Language): List<EtsDeclaration> {
    val storage = topLevelStorage(property, language)
    val initializer = language.expression(property.backingField!!.initializer!!.expression, Scope())
    val global = EtsGlobal(storage, initializer, property.isVar, !DescriptorVisibilities.isPrivate(property.visibility))
    return listOf(global) + if (exportedSetter(property)) listOf(setterFunction(storage)) else emptyList()
}

internal fun writeTopLevelProperty(property: IrProperty, value: EtsExpression, at: SourceSpan,
    language: Language): EtsExpression {
    val storage = topLevelStorage(property, language)
    if (!property.isVar) rejectProperty(property, "Cannot assign an immutable top-level property")
    // Bodies can move to another target file (for example an ArkUI slot method).
    if (exportedSetter(property)) {
        val setter = setterFunction(storage).symbol
        return EtsCall(EtsReference(setter, at), listOf(value), EtsTypes.VOID, at)
    }
    if (at.file != storage.source.file) rejectProperty(property, "Top-level setter is not visible across files")
    return etsDiscard(EtsAssignment(EtsReference(storage, at), value, at), at)
}
