@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.backend

import dev.ets.*
import java.io.File
import java.lang.reflect.Modifier
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.visitors.*

// Reflection follows every target data field, so newly added raw payloads cannot
// silently bypass an otherwise exhaustive node visitor written for an older tree.
fun targetValues(root: Any): List<Any> {
    val values = mutableListOf<Any>()
    fun visit(value: Any?, field: String = "root") {
        when (value) {
            null -> Unit
            is String -> check(field in setOf("file", "sourcePath", "name", "id", "symbolId", "module", "alias", "operator", "label", "value")) {
                "Raw string in target structural field $field"
            }
            is Number, is Boolean, is Char, is Enum<*> -> Unit
            is Map<*, *> -> value.values.forEach { visit(it, field) }
            is Iterable<*> -> value.forEach { visit(it, field) }
            else -> {
                check(value !is IrElement) { "Compiler IR leaked into target tree" }
                check(value.javaClass.packageName == "dev.ets") { "Opaque target payload: ${value.javaClass.name}" }
                values += value
                value.javaClass.declaredFields.filterNot { Modifier.isStatic(it.modifiers) }.forEach {
                    it.isAccessible = true
                    visit(it.get(value), it.name)
                }
            }
        }
    }
    visit(root)
    return values
}

fun lowerFixture(path: String, classpath: String, verify: Boolean = true): EtsProgram =
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", classpath, path)) { module ->
        check(module.files.size == 1)
        val sourceFunctions = module.files.single().declarations.filterIsInstance<IrSimpleFunction>()
        check(sourceFunctions.size >= 4)
        val program: EtsProgram = EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())).lower(module)
        if (verify) {
            EtsValidator().validate(program)
            val values = targetValues(program)
            val functions = values.filterIsInstance<EtsFunction>()
            sourceFunctions.forEach { original ->
                val lowered = functions.single { it.name == original.name.asString() }
                check(lowered.source == SourceSpan(path, original.startOffset, original.endOffset))
                check(lowered.returnType == EtsTypes.NUMBER)
                check(lowered.parameters.map { it.symbol.name } == original.valueParameters.map { it.name.asString() })
                original.valueParameters.zip(lowered.parameters).forEach { (ir, target) ->
                    check(target.symbol.type == EtsTypes.NUMBER)
                    check((ir.defaultValue == null) == (target.defaultValue == null))
                    check(target.symbol.source.file == path)
                    check(target.symbol.source.start == ir.startOffset)
                }
            }
            check(values.any { it is EtsClass }) { "Object declaration missing" }
            val classIds = values.filterIsInstance<EtsClass>().map { it.symbol.id }.toSet()
            val referencedClassIds = values.filterIsInstance<EtsNamedType>().mapNotNull { it.symbolId }
            check(referencedClassIds.isNotEmpty() && referencedClassIds.all { it in classIds }) {
                "Source class types must retain their actual declaration identity"
            }
            check(values.any { it is EtsLoop }) { "While must be structured" }
            check(values.any { it is EtsIf || it is EtsConditional }) { "Conditional missing" }
            val closure = values.filterIsInstance<EtsLambda>().single { lambda -> lambda.parameters.any { it.symbol.name == "value" } }
            val sum = values.filterIsInstance<EtsVariable>().single { it.symbol.name == "sum" }.symbol
            check(targetValues(closure).filterIsInstance<EtsReference>().any { it.symbol == sum }) { "Closure lost captured symbol identity" }
            val expressions = values.filterIsInstance<EtsExpression>()
            check(expressions.isNotEmpty())
            check(values.filterIsInstance<EtsReference>().all { it.symbol.id.isNotBlank() })
            val lexicalSymbols = values.filterIsInstance<EtsSymbol>().filterNot {
                it.external || it.source.file?.startsWith("<stdlib:") == true
            }
            check(lexicalSymbols.groupBy { it.id }.values.all { same -> same.distinct().size == 1 }) {
                "One lexical symbol id describes conflicting declarations/types/sources"
            }

            val sourceDeclarations = sourceFunctions.associate { original ->
                original.symbol to functions.single { it.name == original.name.asString() }
            }
            val sourceCalls = mutableListOf<IrCall>()
            module.acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
                override fun visitCall(expression: IrCall) {
                    if (expression.symbol in sourceDeclarations) sourceCalls += expression
                    expression.acceptChildrenVoid(this)
                }
            })
            check(sourceCalls.isNotEmpty()) { "No resolved source function calls exercised" }
            sourceCalls.forEach { original ->
                val declaration = sourceDeclarations.getValue(original.symbol)
                val callSource = SourceSpan(path, original.startOffset, original.endOffset)
                val call = values.filterIsInstance<EtsCall>().single {
                    it.source == callSource && it.callee is EtsReference
                }
                val reference = call.callee as EtsReference
                check(!reference.symbol.external && !declaration.symbol.external) {
                    "Source function ${declaration.name} must not be marked as an external API"
                }
                check(reference.symbol == declaration.symbol) {
                    "Source call must bind the actual target declaration symbol: ${declaration.name}"
                }
            }

            var injected: SourceSpan? = null
            val ruleSymbol = sourceFunctions.single { it.name.asString() == "ruleValue" }.symbol
            val badRule = object : CallRule {
                override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                    if (call.symbol != ruleSymbol) return null
                    injected = language.source(call)
                    return EtsLiteral("wrong", EtsTypes.STRING, injected!!)
                }
            }
            var returned: EtsProgram? = null
            val failure = try {
                returned = EtsBackend(DiagnosticSink(), listOf(badRule, StandardLibraryRules())).lower(module)
                null
            } catch (error: Unsupported) {
                error.diagnostic.source
            } catch (error: InvalidTarget) {
                error.source
            }
            check(injected != null) { "Wrong-type rule was not exercised" }
            check(returned == null && failure == injected) { "Wrong-type rule must fail during lower, at the call, without a program" }
            check(failure!!.start >= 0 && failure.end > failure.start && failure.file == path)
            println("PASS official IR -> typed AST, source/symbol/closure/default/control/object, source-call binding, wrong-rule rejection: ${File(path).name}")
        }
        program
    }

fun main(args: Array<String>) {
    check(runCatching { Class.forName("dev.ets.EtsPrinter") }.exceptionOrNull() is ClassNotFoundException) {
        "Lower-only run must not have EtsPrinter on its classpath"
    }
    args.drop(1).forEach { lowerFixture(File(it).canonicalPath, args[0]) }
    println("PASS lowering executes without printer class")
}
