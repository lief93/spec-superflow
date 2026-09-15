@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.visitors.*

/** Source-level counterpart of Kotlin/JS's symbol worklist, without JS DCE context. */
internal fun selectSourceDeclarations(module: IrModuleFragment, entry: String): String {
    val declarations = module.files.flatMap { it.declarations }
    val source = declarations.toSet()
    val roots = declarations.filterIsInstance<IrSimpleFunction>().filter {
        symbolName(it) == entry || it.name.asString() == entry
    }
    require(roots.size == 1) { "Source entry '$entry' must resolve to one top-level function; found ${roots.size}" }
    val kept = linkedMapOf<IrDeclaration, String>()
    val pending = ArrayDeque<IrDeclaration>()
    val activeFiles = mutableSetOf<IrFile>()

    fun name(declaration: IrDeclaration): String = (declaration as? IrDeclarationWithName)?.let(::symbolName)
        ?: declaration.javaClass.simpleName
    fun topLevel(declaration: IrDeclaration): IrDeclaration? {
        var current = declaration
        while (true) {
            val property = when (current) {
                is IrSimpleFunction -> current.correspondingPropertySymbol?.owner
                is IrField -> current.correspondingPropertySymbol?.owner
                else -> null
            }
            if (property != null) current = property
            val parent = current.parent
            if (parent is IrFile) return current.takeIf { it in source }
            current = parent as? IrDeclaration ?: return null
        }
    }
    fun enqueue(declaration: IrDeclaration, reason: String) {
        if (declaration !in kept) {
            kept[declaration] = reason
            pending.addLast(declaration)
        }
    }
    fun activate(file: IrFile) {
        if (!activeFiles.add(file)) return
        // File guards initialize even unread storage in declaration order. Keep its
        // dependency closure, not just fields visibly read by the selected entry.
        file.declarations.filterIsInstance<IrProperty>().filter { !it.isConst && it.backingField != null }
            .forEach { enqueue(it, "file initialization: ${file.fileEntry.name}") }
    }
    fun reference(symbol: IrSymbol?, from: IrDeclaration) {
        if (symbol == null || !symbol.isBound) return
        val target = topLevel(symbol.owner as? IrDeclaration ?: return) ?: return
        enqueue(target, "reference from ${name(from)}")
        if (target is IrSimpleFunction || target is IrProperty && !target.isConst || target is IrField)
            activate(target.parent as IrFile)
    }
    enqueue(roots.single(), "entry")
    activate(roots.single().parent as IrFile)
    while (pending.isNotEmpty()) {
        val declaration = pending.removeFirst()
        fun type(type: IrType) {
            val simple = type as? IrSimpleType ?: return
            reference(simple.classifier, declaration)
            simple.arguments.forEach { (it as? IrTypeProjection)?.type?.let(::type) }
        }
        declaration.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrExpression) type(element.type)
                if (element is IrDeclarationReference) reference(element.symbol, declaration)
                if (element is IrMemberAccessExpression<*>) element.typeArguments.forEach { it?.let(::type) }
                when (element) {
                    is IrSimpleFunction -> {
                        type(element.returnType)
                        element.overriddenSymbols.forEach { reference(it, declaration) }
                    }
                    is IrFunction -> type(element.returnType)
                    is IrValueDeclaration -> type(element.type)
                    is IrField -> type(element.type)
                    is IrClass -> element.superTypes.forEach(::type)
                    is IrTypeParameter -> element.superTypes.forEach(::type)
                    is IrTypeAlias -> type(element.expandedType)
                    is IrProperty -> element.overriddenSymbols.forEach { reference(it, declaration) }
                    is IrTypeOperatorCall -> type(element.typeOperand)
                    is IrClassReference -> type(element.classType)
                    is IrVararg -> type(element.varargElementType)
                    is IrFunctionReference -> reference(element.reflectionTarget, declaration)
                }
                element.acceptChildrenVoid(this)
            }
        })
    }
    fun item(declaration: IrDeclaration, reason: String): String {
        val file = sourceFile(declaration)?.fileEntry?.name
        return "{\"symbol\":" + quote(name(declaration)) + ",\"source\":" +
            diagnosticSourceJson(SourceSpan(file, declaration.startOffset, declaration.endOffset)) +
            ",\"reason\":" + quote(reason) + "}"
    }
    val report = "{\"event\":\"source-selection\",\"entry\":" + quote(entry) +
        ",\"kept\":[" + declarations.filter { it in kept }.joinToString(",") { item(it, kept.getValue(it)) } +
        "],\"excluded\":[" + declarations.filter { it !in kept }.joinToString(",") { item(it, "not reachable from entry") } + "]}"
    module.files.forEach { it.declarations.removeAll { declaration -> declaration !in kept } }
    return report
}
