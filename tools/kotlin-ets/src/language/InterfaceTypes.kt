@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.types.classOrNull

// Lossless qualified identity, independent of import aliases and module copies.
internal fun interfaceTypeMarker(owner: IrClass): String = "__etsInterface_" +
    symbolName(owner).toByteArray(Charsets.UTF_8).joinToString("") { "%02x".format(it) }

/** Kotlin/JS uses interface metadata; ETS stores typed nominal membership tags. */
internal fun interfaceTypeMembers(owner: IrClass, at: SourceSpan): List<EtsField> {
    val visited = mutableSetOf<IrClass>()
    fun visit(type: IrClass) {
        if (!visited.add(type)) return
        type.superTypes.mapNotNull { it.classOrNull?.owner }.forEach(::visit)
    }
    visit(owner)
    return visited.filter { it.kind == ClassKind.INTERFACE && sourceFile(it) != null }.sortedBy(::symbolName).map { type ->
        val name = interfaceTypeMarker(type)
        EtsField(EtsSymbol("interface-tag:${at.file}:${at.start}:$name", name, EtsTypes.BOOLEAN, at),
            if (owner.kind == ClassKind.INTERFACE) null else EtsLiteral(true, EtsTypes.BOOLEAN, at), readonly = true)
    }
}
