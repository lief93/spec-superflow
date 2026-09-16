@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.visitors.*

/** Source-level counterpart of Kotlin/JS's symbol worklist, without JS DCE context. */
internal fun selectSourceDeclarations(module: IrModuleFragment, entry: String,
    prepareDeclaration: (IrDeclaration) -> Unit = {}, ignored: Set<IrElement> = emptySet()): String {
    val declarations = module.files.flatMap { it.declarations }
    val source = declarations.toSet()
    val roots = declarations.filterIsInstance<IrSimpleFunction>().filter {
        symbolName(it) == entry || it.name.asString() == entry
    }
    require(roots.size == 1) { "Source entry '$entry' must resolve to one top-level function; found ${roots.size}" }
    val kept = linkedMapOf<IrDeclaration, String>()
    val pending = ArrayDeque<IrDeclaration>()
    val activeFiles = mutableSetOf<IrFile>()
    val members = linkedSetOf<IrSimpleFunction>()
    val visitedMembers = mutableSetOf<IrSimpleFunction>()
    val requiredMembers = mutableSetOf<Pair<IrClass, String>>()
    val virtualMembers = mutableSetOf<String>()
    val referencedFunctions = mutableSetOf<IrSimpleFunction>()
    fun candidate(function: IrSimpleFunction) = function.parent is IrClass && function.correspondingPropertySymbol == null
    fun inherits(owner: IrClass, base: IrClass, visited: MutableSet<IrClass> = mutableSetOf()): Boolean =
        owner == base || visited.add(owner) && owner.superTypes.any {
            it.classOrNull?.owner?.let { parent -> inherits(parent, base, visited) } == true
        }
    fun required(function: IrSimpleFunction): Boolean = function in referencedFunctions ||
        function.overriddenSymbols.any { required(it.owner) } || function.name.asString() in virtualMembers ||
        requiredMembers.any { (owner, member) -> function.name.asString() == member &&
            (function.parent as? IrClass)?.let { inherits(it, owner) } == true }
    fun requireMember(owner: IrClass?, member: String) {
        val changed = if (owner != null) requiredMembers.add(owner to member)
            else virtualMembers.add(member)
        if (changed) members.filter { required(it) && it !in visitedMembers }.forEach { pending.addLast(it) }
    }
    fun requireValueMember(type: IrType, member: String) {
        if (type.isPrimitiveType() || type.isString() || type.isNothing()) return
        requireMember(type.classOrNull?.owner, member)
    }

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
    fun reference(symbol: IrSymbol?, from: IrDeclaration, invoked: Boolean = true) {
        if (symbol == null || !symbol.isBound) return
        val function = symbol.owner as? IrSimpleFunction
        if (invoked && function != null && candidate(function) && referencedFunctions.add(function))
            members.filter { required(it) && it !in visitedMembers }.forEach { pending.addLast(it) }
        val target = topLevel(symbol.owner as? IrDeclaration ?: return) ?: return
        enqueue(target, "reference from ${name(from)}")
        if (target is IrSimpleFunction || target is IrProperty && !target.isConst || target is IrField)
            activate(target.parent as IrFile)
    }
    enqueue(roots.single(), "entry")
    activate(roots.single().parent as IrFile)
    while (pending.isNotEmpty()) {
        val declaration = pending.removeFirst()
        if (declaration in source) prepareDeclaration(declaration)
        fun type(type: IrType) {
            val simple = type as? IrSimpleType ?: return
            reference(simple.classifier, declaration)
            // Collection adapters use key equality/hash without explicit source calls.
            val owner = simple.classOrNull?.owner
            if (owner?.let(::symbolName) in setOf("kotlin.collections.Map", "kotlin.collections.MutableMap",
                "kotlin.collections.Set", "kotlin.collections.MutableSet"))
                (simple.arguments.firstOrNull() as? IrTypeProjection)?.type?.let {
                    requireValueMember(it, "equals"); requireValueMember(it, "hashCode")
                }
            simple.arguments.forEach { (it as? IrTypeProjection)?.type?.let(::type) }
        }
        declaration.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element in ignored) return
                if (element is IrSimpleFunction && candidate(element)) {
                    members.add(element)
                    if (!required(element) || !visitedMembers.add(element)) return
                }
                // These intrinsics dispatch to members without an explicit source call.
                if (element is IrStringConcatenation)
                    element.arguments.forEach { requireValueMember(it.type, "toString") }
                if (element is IrCall) {
                    val function = element.symbol.owner
                    if (symbolName(function) == "kotlin.internal.ir.EQEQ" &&
                        (0 until element.valueArgumentsCount).map { element.getValueArgument(it) }
                            .none { it is IrConst && it.kind == IrConstKind.Null })
                        element.getValueArgument(0)?.let { requireValueMember(it.type, "equals") }
                    if (function.name.asString() in setOf("toString", "equals", "hashCode"))
                        element.dispatchReceiver?.let { requireValueMember(it.type, function.name.asString()) }
                }
                if (element is IrExpression) type(element.type)
                if (element is IrDeclarationReference) reference(element.symbol, declaration)
                if (element is IrMemberAccessExpression<*>) element.typeArguments.forEach { it?.let(::type) }
                when (element) {
                    is IrSimpleFunction -> {
                        type(element.returnType)
                        // An override relationship is not a virtual call on the base.
                        element.overriddenSymbols.forEach { reference(it, declaration, invoked = false) }
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
    module.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrClass) element.declarations.removeAll {
                it is IrSimpleFunction && candidate(it) && !required(it)
            }
            element.acceptChildrenVoid(this)
        }
    })
    return report
}
