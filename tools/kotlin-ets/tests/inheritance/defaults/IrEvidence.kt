@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.defaultArgumentsOriginalFunction
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.file
import org.jetbrains.kotlin.ir.types.classifierOrNull
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinModule(args.drop(1) + listOf("-no-stdlib", "-no-reflect", "-classpath", args[0])) { module ->
        val functions = mutableListOf<IrSimpleFunction>()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                functions.add(declaration); super.visitSimpleFunction(declaration)
            }
        })
        val helpers = functions.filter { it.origin == IrDeclarationOrigin.FUNCTION_FOR_DEFAULT_PARAMETER }
        check(helpers.size == 17)
        helpers.forEach { helper ->
            val original = checkNotNull(helper.defaultArgumentsOriginalFunction)
            val owner = original.parent as IrClass
            check(helper.parent === if (owner.kind == ClassKind.INTERFACE) original.file else owner)
            check(helper.visibility == original.visibility)
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
        val capturedHelpers = helpers.filter { it.file.fileEntry.name.endsWith("/Captures.kt") }
        check(capturedHelpers.size == 4)
        val capturedChild = functions.single { it.name.asString() == "calculate" &&
            (it.parent as? IrClass)?.name?.asString() == "CapturedChild" }.parent as IrClass
        check(capturedChild.declarations.filterIsInstance<IrField>().none {
            it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE
        })
        capturedHelpers.forEach { helper ->
            val owner = helper.parent as IrClass
            val captureFields = owner.declarations.filterIsInstance<IrField>().filter {
                it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE ||
                    it === sourceInnerClassBinding(owner)?.field
            }
            check(captureFields.isNotEmpty())
            var reads = 0
            helper.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
                override fun visitGetField(expression: IrGetField) {
                    if (expression.symbol.owner in captureFields) {
                        check((expression.receiver as? IrGetValue)?.symbol === helper.valueParameters.first().symbol)
                        reads++
                    }
                    super.visitGetField(expression)
                }
                override fun visitGetValue(expression: IrGetValue) {
                    check(expression.symbol !== owner.thisReceiver!!.symbol)
                    super.visitGetValue(expression)
                }
            })
            check(reads > 0)
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
        val bridges = functions.filter { it.origin == ETS_DEFAULT_VISIBILITY_BRIDGE }
        check(bridges.size == 2)
        check(bridges.map { (it.parent as IrClass).name.asString() }.toSet() == setOf("RestrictedChild", "RestrictedSibling"))
        bridges.forEach { bridge ->
            check(bridge.visibility == DescriptorVisibilities.PUBLIC)
            val forwarded = (bridge.body as IrBlockBody).statements.single() as IrReturn
            val call = forwarded.value as IrCall
            check(call.symbol.owner in helpers && call.symbol.owner.visibility == DescriptorVisibilities.PROTECTED)
            check(bridge.valueParameters.size == call.valueArgumentsCount)
            bridge.valueParameters.forEachIndexed { index, parameter ->
                check((call.getValueArgument(index) as IrGetValue).symbol == parameter.symbol)
            }
            bridge.typeParameters.forEachIndexed { index, parameter ->
                check(call.getTypeArgument(index)!!.classifierOrNull == parameter.symbol)
            }
            check(bridge.returnType.classifierOrNull == bridge.typeParameters.single().symbol)
        }
        check(calls == 29) { "Expected 29 provider-helper calls including capture defaults and widening bridges, got $calls" }
        println("PASS common default origins, provider/source identity, explicit receivers, virtual dispatch and two masks; $calls calls")
    }
}
