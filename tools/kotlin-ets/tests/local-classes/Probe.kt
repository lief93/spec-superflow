@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import java.io.File
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.dump

fun main(args: Array<String>) {
    if (args.getOrNull(3) in listOf("capture-values", "capture-heritage")) {
        val inherited = args[3] == "capture-heritage"
        withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
            val file = session.module.files.single()
            val classes = file.declarations.filterIsInstance<IrClass>()
            val captured = classes.filter { owner -> owner.declarations.filterIsInstance<IrField>().any {
                it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE
            } }
            check(captured.size == if (inherited) 1 else 3)
            check(captured.all { !sourceClassIsExported(it) && it.parent === file })
            captured.forEach { owner ->
                val fields = owner.declarations.filterIsInstance<IrField>()
                check(fields.size == 1 && fields.all { it.isFinal && !it.isStatic &&
                    it.origin === LocalDeclarationsLowering.DECLARATION_ORIGIN_FIELD_FOR_CAPTURED_VALUE &&
                    it.startOffset >= owner.startOffset && it.endOffset <= owner.endOffset })
                val constructor = owner.declarations.filterIsInstance<IrConstructor>().single()
                check(constructor.valueParameters.size == 1)
                check(constructor.valueParameters.single().type == fields.single().type)
                val body = (constructor.body as IrBlockBody).statements
                val writes = body.takeWhile { it is IrSetField }.map { it as IrSetField }
                check(writes.size == fields.size)
                writes.forEach { write ->
                    check(write.origin == IrStatementOrigin.STATEMENT_ORIGIN_INITIALIZER_OF_FIELD_FOR_CAPTURED_VALUE)
                    check(write.symbol.owner in fields)
                    check((write.value as IrGetValue).symbol == constructor.valueParameters.single().symbol)
                }
                check(body[writes.size] is IrDelegatingConstructorCall)
            }
            if (!inherited) {
                val counter = captured.single { it.name.asString() == "Counter" }
                check(counter.declarations.filterIsInstance<IrField>().single().type.classOrNull!!.owner.origin === ETS_SHARED_VARIABLE_CELL)
            }
            File(args[2], "captures.ir").writeText(session.module.dump())
            println("PASS official local capture fields, constructor arguments, shared cell identity and source provenance")
        }
        return
    }
    if (args.size > 3) {
        val failure = runCatching {
            withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) {
                error("Unsupported class reached target generation")
            }
        }.exceptionOrNull()
        check(failure is Unsupported) { "Expected source-linked rejection, got $failure" }
        check(failure.diagnostic.message.contains(args[3]))
        check(failure.diagnostic.source.file == args[1])
        check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        println("PASS ${failure.diagnostic}")
        return
    }
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        val file = session.module.files.single()
        File(args[2], "actual.ir").writeText(session.module.dump())
        val classes = file.declarations.filterIsInstance<IrClass>()
        check(classes.map { it.name.asString() }.toSet() ==
            setOf("Envelope", "Node", "PrivateEnvelope", "Hidden", "Local")) { "Classes must be file declarations after lowering" }
        check(classes.all { it.parent === file && it.startOffset >= 0 && it.endOffset > it.startOffset })
        check(classes.filter(::sourceClassIsExported).map { it.name.asString() }.toSet() == setOf("Envelope", "Node"))
        println("PASS nested/local source class ownership and retained source spans")
    }
}
