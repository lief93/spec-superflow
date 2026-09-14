@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.captureconstruction

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val classes = module.files.flatMap { it.declarations }.filterIsInstance<IrClass>()
        for (name in listOf("Counter", "Local", "Stamp", "Collision")) {
            val owner = classes.single { it.name.asString() == name }
            check(!sourceClassIsExported(owner))
            val constructor = owner.constructors.single()
            check(isEtsNativeConstructor(constructor))
            check(constructor.isPrimary == (name != "Local"))
            if (name == "Counter") check(constructor.visibility == DescriptorVisibilities.PRIVATE)
            val fields = owner.declarations.filterIsInstance<IrField>().filter {
                it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE
            }
            check(fields.size == 1)
            val writes = (constructor.body as IrBlockBody).statements.takeWhile { it is IrSetField }.map { it as IrSetField }
            check(writes.map { it.symbol.owner }.toSet() == fields.toSet() && writes.size == 1)
            if (name in listOf("Counter", "Local")) {
                check(constructor.valueParameters.any { it.name.asString() == "\$trace" })
                check(fields.none { it.name.asString() == "\$trace" })
            }
            writes.forEach { write ->
                check(write.origin === IrStatementOrigin.STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE)
                check((write.receiver as IrGetValue).symbol == owner.thisReceiver!!.symbol)
                val parameter = (write.value as IrGetValue).symbol.owner as IrValueParameter
                check(parameter.parent === constructor && parameter.type == write.symbol.owner.type)
            }
        }
        for (name in listOf("Item", "Root")) {
            val owner = classes.single { it.name.asString() == name }
            val binding = checkNotNull(sourceInnerClassBinding(owner))
            check(binding.constructor === owner.constructors.single() && isEtsNativeConstructor(binding.constructor))
            check(binding.constructor.isPrimary == (name == "Item"))
            val write = (binding.constructor.body as IrBlockBody).statements.first() as IrSetField
            check(write.symbol === binding.field.symbol && (write.value as IrGetValue).symbol === binding.parameter.symbol)
        }
        val functions = classes.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        check(functions.count { it.origin.name == "ETS_SECONDARY_CONSTRUCTOR" } == 7)
        val entries = classes.single { it.name.asString() == "Entries" }
        check(isEtsDispatchConstructor(entries.constructors.single()))
        check(entries.declarations.filterIsInstance<IrField>().none {
            it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE
        })
        val sourceFiles = module.files.toSet()
        module.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitConstructorCall(expression: IrConstructorCall) {
                val target = expression.symbol.owner
                if (target.fileOrNull in sourceFiles) check(target in target.parentAsClass.declarations)
                super.visitConstructorCall(expression)
            }
        })
        fun lower() = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        val program = lower()
        val collision = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.name == "Collision" }
        val factory = collision.members.filterIsInstance<EtsFunction>().single { it.static }
        check(factory.parameters.last().symbol.name == "\$seed")
        check(factory.parameters.first().symbol.name != "\$seed")
        val owner = classes.single { it.name.asString() == "Local" }
        val body = owner.constructors.single().body as IrBlockBody
        val write = body.statements.removeAt(0)
        val failure = try { runCatching { lower() }.exceptionOrNull() } finally { body.statements.add(0, write) }
        check(failure is Unsupported && failure.diagnostic.message.contains("official initialization prefix"))
        File(args[1], "lowered.ir").writeText(module.dump())
        println("PASS four official capture fields, constructor-only captures, two outer bindings, two non-primary native roots, seven factories and missing-prefix rejection")
    }
}
