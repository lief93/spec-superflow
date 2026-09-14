@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.defaultArgumentsOriginalFunction
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.file
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinModule(args.drop(1) + listOf("-no-stdlib", "-no-reflect", "-classpath", args[0])) { module ->
        val helpers = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .filter { it.origin == IrDeclarationOrigin.FUNCTION_FOR_DEFAULT_PARAMETER }
        check(helpers.size == 10)
        helpers.forEach { helper ->
            val original = checkNotNull(helper.defaultArgumentsOriginalFunction)
            check(helper.file === original.file)
            check(helper.startOffset == original.startOffset && helper.endOffset == original.endOffset)
            check(helper.dispatchReceiverParameter == null)
            check(helper.valueParameters.first().origin == IrDeclarationOrigin.MOVED_DISPATCH_RECEIVER)
            check(original.valueParameters.all { it.defaultValue == null })
            var dispatches = 0
            helper.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitCall(expression: IrCall) {
                    if (expression.origin == IrStatementOrigin.DEFAULT_DISPATCH_CALL) {
                        check(expression.symbol == original.symbol)
                        check(expression.dispatchReceiver != null)
                        check(expression.arguments.all { it != null })
                        dispatches++
                    }
                    super.visitCall(expression)
                }
            })
            check(dispatches == 1)
        }
        val masks = helpers.single { it.defaultArgumentsOriginalFunction!!.name.asString() == "sum" }
            .valueParameters.filter { it.origin == IrDeclarationOrigin.MASK_FOR_DEFAULT_FUNCTION }
        check(masks.size == 2)
        var calls = 0
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                if (declaration.origin == IrDeclarationOrigin.FUNCTION_FOR_DEFAULT_PARAMETER) check(declaration in helpers)
                super.visitSimpleFunction(declaration)
            }
            override fun visitCall(expression: IrCall) {
                if (expression.symbol.owner.origin == IrDeclarationOrigin.FUNCTION_FOR_DEFAULT_PARAMETER) {
                    check(expression.symbol.owner in helpers)
                    check(expression.arguments.all { it != null })
                    check(expression.typeArguments.all { it != null })
                    calls++
                }
                super.visitCall(expression)
            }
        })
        check(calls == 18) { "Expected the fixture's 18 omitted-argument calls, got $calls" }
        println("PASS common default origins, provider/source identity, explicit receivers, virtual dispatch and two masks; $calls calls")
    }
}
