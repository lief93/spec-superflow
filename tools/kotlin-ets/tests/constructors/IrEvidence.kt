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
            .filterNot { it.parentAsClass.constructors.any(::isEtsDispatchConstructor) }
        check(factories.size == 17) { "Expected seventeen source secondary factories, got ${factories.size}" }
        val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        val roots = classes.flatMap { it.constructors.toList() }.filterNot { it.isPrimary || isEtsDispatchConstructor(it) }
        check(roots.size == 7) { "Expected seven original secondary allocation roots, got ${roots.size}" }
        roots.forEach {
            check(isEtsNativeConstructor(it) && it.parentAsClass.constructors.single() === it)
            check(it.startOffset >= 0 && it.endOffset > it.startOffset)
            check(it.parameters.all { parameter -> parameter.parent === it })
        }
        val dispatchers = classes.flatMap { it.constructors.toList() }.filter(::isEtsDispatchConstructor)
        check(dispatchers.size == 6) { "Expected six multi-entry native constructors, got ${dispatchers.size}" }
        dispatchers.forEach { constructor ->
            check(!constructor.isPrimary && isEtsNativeConstructor(constructor))
            check(constructor.parentAsClass.constructors.single() === constructor)
            check(constructor.valueParameters.first().name.asString() == "__constructor")
            check(constructor.valueParameters.all { it.parent === constructor })
            check(constructor.parentAsClass.declarations.none { it is IrSimpleFunction && it.name.asString() == "initialize" })
        }
        for ((childName, baseName) in listOf("RootChild" to "RootBase", "ConcreteNative" to "AbstractNative")) {
            val child = classes.single { it.name.asString() == childName }
            val base = classes.single { it.name.asString() == baseName }
            val delegation = (child.constructors.single().body as IrBlockBody).statements.first() as IrDelegatingConstructorCall
            check(delegation.symbol === base.constructors.single().symbol)
            check(isEtsNativeConstructor(delegation.symbol.owner) && !delegation.symbol.owner.isPrimary)
        }
        factories.forEach { factory ->
            val original = factory.attributeOwnerId as IrConstructor
            check(!original.isPrimary && original.parent === factory.parent)
            check(factory.file === original.file && factory.startOffset == original.startOffset && factory.endOffset == original.endOffset)
            check(factory.dispatchReceiverParameter == null)
            check(factory.visibility == original.visibility)
            check(factory.valueParameters.map { it.name } == original.valueParameters.map { it.name })
            check(isEtsNativeConstructor(factory.parentAsClass.constructors.single()))
            val body = factory.body as IrBlockBody
            val instance = body.statements.first() as IrVariable
            when (val allocation = instance.initializer) {
                is IrConstructorCall -> check(isEtsNativeConstructor(allocation.symbol.owner) && allocation.symbol.owner.parent === factory.parent)
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
                check(isEtsNativeConstructor(expression.symbol.owner))
                super.visitConstructorCall(expression)
            }
            override fun visitDelegatingConstructorCall(expression: IrDelegatingConstructorCall) {
                check(isEtsNativeConstructor(expression.symbol.owner))
                super.visitDelegatingConstructorCall(expression)
            }
            override fun visitGetValue(expression: IrGetValue) {
                val constructor = expression.symbol.owner.parent as? IrConstructor ?: return
                check(constructor in constructor.parentAsClass.constructors.toList()) {
                    "Value still refers to removed source constructor: ${expression.symbol.owner.name}"
                }
            }
        })
        println("PASS seventeen single-root factories, seven original secondary native roots, six multi-entry native constructors, exact cross-class super symbols and remapped constructor parameters")
    }
}
