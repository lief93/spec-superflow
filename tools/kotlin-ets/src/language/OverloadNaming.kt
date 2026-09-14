@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.backend.common.bridges.generateBridges
import org.jetbrains.kotlin.ir.backend.js.lower.IrBasedFunctionHandle
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.allOverridden
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

    fun bridges(function: IrSimpleFunction): List<Pair<IrSimpleFunction, IrSimpleFunction>> {
        if (function.modality == Modality.ABSTRACT) {
            // Common emits no abstract bridge bodies. ETS still requires declarations
            // for the inherited entries that a source abstract override joins.
            return function.allOverridden().filter { !it.isFakeOverride && name(it) != name(function) }
                .distinctBy(::name).map { it to function }
        }
        return generateBridges(IrBasedFunctionHandle(function)) {
            BridgeSignature(it.function, name(it.function))
        }.map { it.from.function to it.to.function }
    }

    private class BridgeSignature(val function: IrSimpleFunction, private val name: String) {
        override fun equals(other: Any?): Boolean = other is BridgeSignature && name == other.name
        override fun hashCode(): Int = name.hashCode()
    }

    private fun prepare(module: IrModuleFragment) {
        val reserved = mutableSetOf<String>()
        val functions = mutableListOf<IrSimpleFunction>()
        val classes = mutableListOf<IrClass>()
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
                if (element is IrClass) classes += element
                if (element is IrDeclarationWithName && !element.name.isSpecial) reserved.add(element.name.asString())
                if (element is IrSimpleFunction && !element.isFakeOverride && element.correspondingPropertySymbol == null &&
                    (element.parent is IrFile || element.parent is IrClass)) functions += element
                element.acceptChildrenVoid(this)
            }
        })
        val table = NameTable<IrSimpleFunction>(reserved = reserved)
        val sourceOrder = compareBy<IrSimpleFunction>({ sourceFile(it)!!.fileEntry.name }, { it.startOffset }, { it.endOffset })
        val ordered = functions.sortedWith(sourceOrder)
        val groups = ordered.filter { it.parent is IrFile }.groupBy {
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
        val memberGroups = memberGroups(classes, ordered.filter { it.parent is IrClass }, sourceOrder)
        for (slots in (groups.map { it.map(::listOf) } + memberGroups).sortedWith(compareBy { group ->
            group.firstOrNull()?.firstOrNull()?.let { ordered.indexOf(it) } ?: -1
        })) {
            if (slots.size < 2) continue
            val group = slots.flatten()
            val reason = when {
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
            table.declareStableName(slots.first().first(), original)
            slots.first().forEach { names[it] = original }
            for (slot in slots.drop(1)) {
                val name = table.declareFreshName(slot.first(), original)
                slot.forEach { names[it] = name }
            }
        }
    }

    private fun memberGroups(classes: List<IrClass>, methods: List<IrSimpleFunction>, order: Comparator<IrSimpleFunction>): List<List<List<IrSimpleFunction>>> {
        val real = methods.toSet()
        fun declarations(function: IrSimpleFunction) = function.allOverridden(includeSelf = true).filter { !it.isFakeOverride }
        val scopes = classes.flatMap { owner -> owner.declarations.filterIsInstance<IrSimpleFunction>()
            .filter { it.correspondingPropertySymbol == null }.groupBy { it.name }.values }
        val edges = scopes.flatten().map { declarations(it).filter { method -> method in real } }
        // The frontend has already resolved overrides, including interface joins.
        val families = components(methods.map(::listOf) + edges).flatMap { family ->
            if (family.groupBy { it.parent }.values.none { it.size > 1 }) listOf(family)
            else {
                // A generic override can implement two independent ancestor slots.
                // Choose one body spelling; common generateBridges retains the other entries.
                val roots = family.filter { declarations(it).none { parent -> parent !== it && parent in real } }.toSet()
                family.groupBy { declarations(it).filter { parent -> parent in roots }.minWith(order) }.values.toList()
            }
        }
        val representatives = families.flatMap { family -> family.map { it to family.minWith(order) } }.toMap()
        val byRepresentative = families.associateBy { it.minWith(order) }
        val collisions = scopes.map { scope ->
            val all = scope.flatMap(::declarations).distinct()
            if (scope.size > 1 && all.any { it !in real }) all.filter { it in real }.forEach {
                unsupported[it] = "Overloads involving external inherited declarations require a target bridge"
            }
            all.mapNotNull { representatives[it] }.distinct()
        }
        return components(representatives.values.distinct().map(::listOf) + collisions).map { group ->
            group.sortedWith(order).map { byRepresentative.getValue(it).sortedWith(order) }
        }
    }

    /** Connected override slots and target spelling conflicts, keyed by IR identity. */
    private fun components(groups: List<List<IrSimpleFunction>>): List<List<IrSimpleFunction>> {
        val parents = IdentityHashMap<IrSimpleFunction, IrSimpleFunction>()
        fun root(value: IrSimpleFunction): IrSimpleFunction {
            val parent = parents.getOrPut(value) { value }
            if (parent === value) return value
            return root(parent).also { parents[value] = it }
        }
        groups.forEach { group -> group.firstOrNull()?.let { first ->
            group.forEach { parents[root(it)] = root(first) }
        } }
        return parents.keys.toList().groupBy(::root).values.toList()
    }
}
