@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.jvm.JvmLoweredDeclarationOrigin
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.dump
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    val failure = runCatching {
        withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
            if (args.getOrNull(3) == "secondary") {
                val owner = session.module.files.single().declarations.filterIsInstance<IrClass>().single { it.name.asString() == "Inner" }
                val binding = checkNotNull(sourceInnerClassBinding(owner))
                check(owner.declarations.filterIsInstance<IrConstructor>() == listOf(binding.constructor))
                check(isEtsNativeConstructor(binding.constructor))
                val factory = owner.declarations.filterIsInstance<IrSimpleFunction>().single { it.origin.name == "ETS_SECONDARY_CONSTRUCTOR" }
                check(factory.valueParameters.first().origin === JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS)
                check(factory.valueParameters.first().type == binding.parameter.type)
                File(args[2], "secondary.ir").writeText(session.module.dump())
                println("PASS secondary factory retains original inner constructor and explicit outer parameter")
                return@withKotlinFrontend
            }
            if (args.size > 3) error("Unsupported inner class reached target generation")
            val file = session.module.files.single()
            val classes = file.declarations.filterIsInstance<IrClass>()
            val inner = classes.single { it.name.asString() == "Inner" }
            val outer = classes.single { it.name.asString() == "Outer" }
            val field = inner.declarations.filterIsInstance<IrField>().single()
            val constructor = inner.declarations.filterIsInstance<IrConstructor>().single()
            val parameter = constructor.valueParameters.first()
            val binding = checkNotNull(sourceInnerClassBinding(inner))
            check(binding.outer === outer && binding.field === field && binding.constructor === constructor && binding.parameter === parameter)
            check(binding.source.file == args[1] && binding.source.start == inner.startOffset && binding.source.end == inner.endOffset)
            check(sourceInnerClassBinding(outer) == null)
            check(field.origin === IrDeclarationOrigin.FIELD_FOR_OUTER_THIS)
            check(field.isFinal && !field.isStatic && field.type.classOrNull?.owner === outer)
            check(parameter.origin === JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS)
            check(parameter.type == field.type)
            check(inner.parent === file && sourceClassIsExported(inner))
            val body = (constructor.body as IrBlockBody).statements
            val write = body.first() as IrSetField
            check(write.symbol === field.symbol)
            check((write.receiver as IrGetValue).symbol === inner.thisReceiver!!.symbol)
            check((write.value as IrGetValue).symbol === parameter.symbol)
            check(body[1] is IrDelegatingConstructorCall)
            var calls = 0
            session.module.acceptVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrConstructorCall && element.symbol.owner.parent === inner) {
                        check(element.symbol === constructor.symbol && element.dispatchReceiver == null)
                        check(element.getValueArgument(0)!!.type.classOrNull?.owner === outer)
                        calls++
                    }
                    element.acceptChildrenVoid(this)
                }
            })
            check(calls == 2)
            File(args[2], "actual.ir").writeText(session.module.dump())
            println("PASS official inner field, constructor prefix, call receiver threading and original ownership")
        }
    }.exceptionOrNull()
    if (args.size <= 3 || args[3] == "secondary") { if (failure != null) throw failure; return }
    check(failure is Unsupported && failure.diagnostic.message.contains(args[3])) { "$failure" }
    check(failure.diagnostic.source.file == args[1] && failure.diagnostic.source.start >= 0)
    println("PASS ${failure.diagnostic}")
}
