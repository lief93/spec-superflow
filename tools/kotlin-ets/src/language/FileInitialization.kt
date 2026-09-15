@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.security.MessageDigest
import org.jetbrains.kotlin.ir.declarations.*

internal fun lazyTopLevelProperty(property: IrProperty): Boolean =
    !property.isConst && (property.parent as? IrFile)?.let(::requiresFileInitialization) == true

private fun initializationSource(file: IrFile) = SourceSpan(file.fileEntry.name, 0, 0)
private fun initializationName(file: IrFile): String = "__etsInitialize_" +
    MessageDigest.getInstance("SHA-256").digest(file.fileEntry.name.toByteArray(Charsets.UTF_8))
        .take(8).joinToString("") { "%02x".format(it.toInt() and 255) }

internal fun fileInitializationCall(file: IrFile): EtsExpressionStatement {
    val at = initializationSource(file)
    val symbol = etsFunctionSymbol(initializationName(file), emptyList(), EtsTypes.VOID, at)
    return EtsExpressionStatement(EtsCall(EtsReference(symbol), emptyList(), EtsTypes.VOID, at))
}

internal fun lowerFileInitialization(file: IrFile, language: Language): List<EtsDeclaration> {
    if (!requiresFileInitialization(file)) return emptyList()
    val at = initializationSource(file)
    val name = initializationName(file)
    val state = EtsSymbol("file-init:${at.file}", name + "_state", EtsTypes.NUMBER, at)
    fun number(value: Int) = EtsLiteral(value, EtsTypes.NUMBER, at)
    fun isState(value: Int) = EtsBinary("===", EtsReference(state), number(value), EtsTypes.BOOLEAN, at)
    fun setState(value: Int) = EtsExpressionStatement(EtsAssignment(EtsReference(state), number(value), at))
    val caught = EtsSymbol("file-init-error:${at.file}", "__etsCaught", EtsTypes.OBJECT, at)
    val error = EtsCast(EtsReference(caught), targetErrorType, at)
    val category = EtsMember(error, "name", EtsTypes.STRING, at)
    fun hasCategory(value: String) = EtsBinary("===", category, EtsLiteral(value, EtsTypes.STRING, at), EtsTypes.BOOLEAN, at)
    val alreadyWrapped = EtsBinary("||", hasCategory("ExceptionInInitializerError"), hasCategory("NoClassDefFoundError"), EtsTypes.BOOLEAN, at)
    val assignments = file.declarations.filterIsInstance<IrProperty>().filter { lazyTopLevelProperty(it) && it.backingField != null }.map { property ->
        val storage = topLevelStorage(property, language)
        EtsExpressionStatement(EtsAssignment(EtsReference(storage),
            language.expression(property.backingField!!.initializer!!.expression, Scope()), storage.source))
    }
    // Re-entry by an initializer's own helper observes already assigned fields,
    // as with JVM file-class initialization. Failed files never become ready.
    val body = listOf(
        EtsIf(listOf(EtsBranch(isState(3), listOf(EtsThrow(namedTargetFailure("NoClassDefFoundError", at), at)))), at),
        EtsIf(listOf(EtsBranch(EtsBinary("!==", EtsReference(state), number(0), EtsTypes.BOOLEAN, at), listOf(EtsReturn(null, at)))), at),
        setState(1),
        EtsTry(assignments + setState(2), EtsCatch(caught, listOf(setState(3),
            EtsIf(listOf(EtsBranch(alreadyWrapped, listOf(EtsThrow(error, at)))), at),
            EtsThrow(namedTargetFailure("ExceptionInInitializerError", at, EtsMember(error, "message", EtsTypes.STRING, at)), at))), source = at))
    return listOf(EtsGlobal(state, number(0), true), EtsFunction(name, emptyList(), EtsTypes.VOID, body, at, exported = true))
}
