@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid

private class RecordingLanguage(private val inner: Language) : Language {
    val classes = mutableListOf<IrClass>()
    val functions = mutableListOf<IrSimpleFunction>()
    val calls = mutableListOf<IrCall>()
    override val callRules get() = inner.callRules
    override fun source(element: IrElement) = inner.source(element)
    override fun type(type: IrType) = inner.type(type)
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        if (expression is IrCall) calls.add(expression)
        return inner.expression(expression, scope)
    }
    override fun statements(body: org.jetbrains.kotlin.ir.expressions.IrBody, scope: Scope) = inner.statements(body, scope)
    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction {
        functions.add(function)
        return inner.function(function, scope)
    }
    override fun clazz(declaration: IrClass): EtsClass {
        classes.add(declaration)
        return inner.clazz(declaration)
    }
}

private fun plusCalls(root: IrElement): List<IrCall> {
    val result = mutableListOf<IrCall>()
    root.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrCall && element.symbol.owner.fqNameWhenAvailable?.asString() in
                setOf("kotlin.plus", "kotlin.String.plus")) result.add(element)
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

fun main(args: Array<String>) {
    withKotlinFrontend(listOf(args[0], "-no-stdlib", "-no-reflect", "-classpath", args[1])) { session ->
        val module = session.module
        val file = module.files.single { it.fileEntry.name == args[0] }
        check(plusCalls(module).isEmpty()) { "String plus must already be lowered before IrToEts" }
        val diagnostics = DiagnosticSink(file.fileEntry.name)
        val inner = LanguageLowering(diagnostics, listOf(StandardLibraryRules()), session.types)
        val recording = RecordingLanguage(inner)
        val program = IrToEts.program(listOf(module), recording, diagnostics)
        check(program.files.single().sourcePath == args[0])
        val sourceClasses = file.declarations.filterIsInstance<IrClass>()
        val sourceFunctions = file.declarations.filterIsInstance<IrSimpleFunction>()
        check(recording.classes.isNotEmpty()) { "IrClassToEts must delegate IrClass nodes to Language" }
        check(recording.classes.all { declaration -> sourceClasses.any { it === declaration } }) {
            "IrToEts must pass the same IrClass instances Language sees, not rewritten copies"
        }
        check(sourceClasses.all { original -> recording.classes.any { it === original } })
        sourceFunctions.forEach { original ->
            check(recording.functions.any { it === original }) {
                "IrFunctionToEts must pass the same IrSimpleFunction instance Language sees"
            }
            val lowered = IrFunctionToEts.lower(original, inner)
            check(lowered.name == original.name.asString())
            check(lowered.source.file == args[0])
        }
        val viaBackend = EtsBackend(DiagnosticSink(file.fileEntry.name), listOf(StandardLibraryRules()), session.types)
            .lower(listOf(module))
        check(viaBackend.files.single().sourcePath == program.files.single().sourcePath)
        check(viaBackend.files.single().declarations.map { it::class to when (it) {
            is EtsFunction -> it.name
            is EtsClass -> it.name
            else -> it.source
        } } == program.files.single().declarations.map { it::class to when (it) {
            is EtsFunction -> it.name
            is EtsClass -> it.name
            else -> it.source
        } })
        val files = IrModuleToEts.lower(module, inner, diagnostics)
        check(files.single().sourcePath == program.files.single().sourcePath)
        println("PASS IrToEts seam: classes=${recording.classes.size}; functions=${recording.functions.size}; no String.plus; names preserved")
    }
}
