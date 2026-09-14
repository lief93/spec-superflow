@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.primaryConstructor
import org.jetbrains.kotlin.ir.visitors.*

/** Select emitted bindings without changing source names, offsets or generic owners. */
class ClassNaming(private val functions: OverloadNaming) {
    private val prepared = Collections.newSetFromMap(IdentityHashMap<IrModuleFragment, Boolean>())
    private val names = IdentityHashMap<IrClass, String>()

    fun name(declaration: IrClass): String {
        val file = sourceFile(declaration) ?: return declaration.name.asString()
        if (prepared.add(file.module)) prepare(file.module)
        return names[declaration] ?: declaration.name.asString()
    }

    private fun prepare(module: IrModuleFragment) {
        val reserved = mutableSetOf<String>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrDeclarationWithName && !element.name.isSpecial) reserved += element.name.asString()
                element.acceptChildrenVoid(this)
            }
        })
        val declarations = module.files.flatMap { it.declarations }
        val fixed = declarations.filterIsInstance<IrSimpleFunction>().map { functions.name(it) }.toSet()
        reserved.addAll(fixed)
        val table = NameTable<IrClass>(reserved = reserved)
        val shadowed = shadowedClassValues(module)
        val ordered = declarations.filterIsInstance<IrClass>().sortedWith(
            compareBy({ sourceFile(it)!!.fileEntry.name }, { it.startOffset }, { it.endOffset }))
        for (group in ordered.groupBy { it.name }.values) {
            val original = group.first().name.asString()
            val stable = group.firstOrNull { it !in shadowed }?.takeUnless { original in fixed }
            if (stable != null) {
                table.declareStableName(stable, original)
                names[stable] = original
            }
            for (declaration in group.filter { it !== stable }) names[declaration] = table.declareFreshName(declaration, original)
        }
    }

    private fun shadowedClassValues(module: IrModuleFragment): Set<IrClass> {
        val shadowed = Collections.newSetFromMap(IdentityHashMap<IrClass, Boolean>())
        val scopes = mutableListOf<Set<String>>()
        fun scoped(values: List<IrValueDeclaration>, visit: () -> Unit) {
            scopes += values.filterNot { it.name.isSpecial ||
                it.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE ||
                it.origin == IrDeclarationOrigin.IR_TEMPORARY_VARIABLE_FOR_INLINED_EXTENSION_RECEIVER
            }.map { it.name.asString() }.toSet()
            try { visit() } finally { scopes.removeAt(scopes.lastIndex) }
        }
        // Target const/let bindings shadow the whole emitted block, including their
        // initializers. Statement composites share their containing block's scope.
        fun bindings(statements: List<IrStatement>): List<IrVariable> = statements.flatMap {
            when (it) { is IrVariable -> listOf(it); is IrComposite -> bindings(it.statements); else -> emptyList() }
        }
        fun use(declaration: IrClass?) {
            if (declaration != null && scopes.any { declaration.name.asString() in it }) shadowed += declaration
        }
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                when (element) {
                    is IrConstructorCall -> use(element.symbol.owner.parent as? IrClass)
                    is IrGetObjectValue -> use(element.symbol.owner)
                    is IrCall -> if (element.dispatchReceiver == null) use(element.symbol.owner.parent as? IrClass)
                    is IrTypeOperatorCall -> if (element.operator in setOf(IrTypeOperator.INSTANCEOF,
                        IrTypeOperator.NOT_INSTANCEOF, IrTypeOperator.CAST, IrTypeOperator.SAFE_CAST))
                        use(element.typeOperand.classOrNull?.owner)
                }
                element.acceptChildrenVoid(this)
            }
            override fun visitFunction(declaration: IrFunction) = scoped(
                declaration.valueParameters + listOfNotNull(declaration.extensionReceiverParameter)
            ) { super.visitFunction(declaration) }
            override fun visitBlockBody(body: IrBlockBody) = scoped(bindings(body.statements)) { super.visitBlockBody(body) }
            override fun visitBlock(expression: IrBlock) = scoped(bindings(expression.statements)) { super.visitBlock(expression) }
            override fun visitComposite(expression: IrComposite) = scoped(bindings(expression.statements)) { super.visitComposite(expression) }
            override fun visitCatch(aCatch: IrCatch) = scoped(listOf(aCatch.catchParameter)) { super.visitCatch(aCatch) }
            override fun visitField(declaration: IrField) = scoped(
                if (declaration.isStatic) emptyList() else
                    (declaration.parent as? IrClass)?.primaryConstructor?.valueParameters.orEmpty()
            ) { super.visitField(declaration) }
            override fun visitAnonymousInitializer(declaration: IrAnonymousInitializer) = scoped(
                (declaration.parent as? IrClass)?.primaryConstructor?.valueParameters.orEmpty()
            ) { super.visitAnonymousInitializer(declaration) }
        })
        return shadowed
    }
}
