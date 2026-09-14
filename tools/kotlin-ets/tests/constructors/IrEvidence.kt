@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinModule(args.drop(1) + listOf("-no-stdlib", "-no-reflect", "-classpath", args[0])) { module ->
        val factories = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
            .flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.attributeOwnerId is IrConstructor }
        check(factories.size == 11) { "Expected eleven source secondary constructors, got ${factories.size}" }
        factories.forEach { factory ->
            val original = factory.attributeOwnerId as IrConstructor
            check(!original.isPrimary && original.parent === factory.parent)
            check(factory.file === original.file && factory.startOffset == original.startOffset && factory.endOffset == original.endOffset)
            check(factory.dispatchReceiverParameter == null)
            check(factory.visibility == original.visibility)
            check(factory.valueParameters.map { it.name } == original.valueParameters.map { it.name })
            check(factory.parentAsClass.constructors.single().isPrimary)
            val body = factory.body as IrBlockBody
            val instance = body.statements.first() as IrVariable
            when (val allocation = instance.initializer) {
                is IrConstructorCall -> check(allocation.symbol.owner.isPrimary && allocation.symbol.owner.parent === factory.parent)
                is IrCall -> check(allocation.symbol.owner in factories && allocation.symbol.owner.parent === factory.parent)
                else -> error("Constructor must allocate through its resolved same-class delegation")
            }
            factory.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitGetValue(expression: IrGetValue) {
                    check(expression.symbol != factory.parentAsClass.thisReceiver!!.symbol)
                    check(expression.symbol.owner.parent !== original)
                }
                override fun visitReturn(expression: IrReturn) {
                    if (expression.returnTargetSymbol == factory.symbol) check((expression.value as IrGetValue).symbol === instance.symbol)
                    super.visitReturn(expression)
                }
            })
        }
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitConstructorCall(expression: IrConstructorCall) {
                check(expression.symbol.owner.isPrimary)
                super.visitConstructorCall(expression)
            }
        })
        println("PASS eleven symbol-bound factories, original source/parameters/visibility, one same-class allocation per chain link, remapped this/returns")
    }
}
