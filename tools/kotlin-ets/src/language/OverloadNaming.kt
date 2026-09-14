@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.*

/** Allocate before lowering bodies so resolved calls never depend on visitation order. */
class OverloadNaming {
    private val prepared = Collections.newSetFromMap(IdentityHashMap<IrModuleFragment, Boolean>())
    private val names = IdentityHashMap<IrSimpleFunction, String>()
    private val unsupported = IdentityHashMap<IrSimpleFunction, String>()

    fun name(function: IrSimpleFunction): String {
        val file = sourceFile(function) ?: return function.name.asString()
        if (prepared.add(file.module)) prepare(file.module)
        unsupported[function]?.let { message ->
            throw Unsupported(Diagnostic("UNSUPPORTED", message,
                SourceSpan(file.fileEntry.name, function.startOffset, function.endOffset)))
        }
        return names[function] ?: function.name.asString()
    }

    private fun prepare(module: IrModuleFragment) {
        val reserved = mutableSetOf<String>()
        val functions = mutableListOf<IrSimpleFunction>()
        val callsByFile = IdentityHashMap<IrFile, MutableSet<IrSimpleFunction>>()
        module.acceptVoid(object : IrElementVisitorVoid {
            private var currentFile: IrFile? = null
            override fun visitFile(declaration: IrFile) {
                val previous = currentFile
                currentFile = declaration
                super.visitFile(declaration)
                currentFile = previous
            }
            override fun visitCall(expression: IrCall) {
                val callee = expression.symbol.owner
                val file = currentFile
                if (file != null && callee.parent is IrFile && callee.parent !== file &&
                    !DescriptorVisibilities.isPrivate(callee.visibility))
                    callsByFile.getOrPut(file) { mutableSetOf() }.add(callee)
                super.visitCall(expression)
            }
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
                if (element is IrSimpleFunction && !element.isFakeOverride && element.correspondingPropertySymbol == null &&
                    (element.parent is IrFile || element.parent is IrClass)) functions += element
                element.acceptChildrenVoid(this)
            }
        })
        val table = NameTable<IrSimpleFunction>(reserved = reserved)
        val sourceOrder = compareBy<IrSimpleFunction>({ sourceFile(it)!!.fileEntry.name }, { it.startOffset }, { it.endOffset })
        val ordered = functions.sortedWith(sourceOrder)
        val groups = ordered.groupBy {
            val parent = it.parent
            (if (parent is IrFile) parent.packageFqName else parent) to it.name
        }.values.flatMap { group ->
            if (group.first().parent !is IrFile) listOf(group) else {
                // Union same-file groups with the package-visible group first.
                val visibleFiles = group.filterNot { DescriptorVisibilities.isPrivate(it.visibility) }
                    .map { it.parent }.toSet()
                val (visible, local) = group.partition { it.parent in visibleFiles }
                var shared = visible
                val separate = mutableListOf<List<IrSimpleFunction>>()
                for (fileGroup in local.groupBy { it.parent }.values) {
                    // Only the first shared declaration retains the source spelling.
                    // Link a private file only if its resolved import would collide.
                    val retained = shared.firstOrNull()
                    val file = fileGroup.first().parent as IrFile
                    if (retained != null && callsByFile[file]?.contains(retained) == true)
                        shared = (shared + fileGroup).sortedWith(sourceOrder)
                    else separate += fileGroup
                }
                listOf(shared) + separate
            }
        }
        for (group in groups) {
            if (group.size < 2) continue
            val parent = group.first().parent
            val reason = when {
                parent is IrClass && (parent.kind != ClassKind.CLASS || parent.modality != Modality.FINAL ||
                    parent.superTypes.any { it.classOrNull?.owner?.fqNameWhenAvailable?.asString() != "kotlin.Any" }) ->
                    "Overloads require a final class without inheritance"
                group.any { it.modality != Modality.FINAL || it.overriddenSymbols.isNotEmpty() } ->
                    "Virtual and overridden overloads are not supported"
                group.any { it.startOffset < 0 || it.endOffset <= it.startOffset } ->
                    "Overloads require original source declaration positions"
                group.any { it.extensionReceiverParameter != null || it.contextReceiverParametersCount != 0 ||
                    it.valueParameters.any { parameter -> parameter.defaultValue != null || parameter.varargElementType != null } } ->
                    "Overloaded extension, context, default and vararg parameters are not supported"
                group.any { it.isSuspend || it.typeParameters.any { parameter -> parameter.isReified } } ->
                    "Suspend and reified overloads are not supported"
                else -> null
            }
            if (reason != null) {
                group.forEach { unsupported[it] = reason }
                continue
            }
            val original = group.first().name.asString()
            table.declareStableName(group.first(), original)
            names[group.first()] = original
            for (function in group.drop(1)) names[function] = table.declareFreshName(function, original)
        }
    }
}
