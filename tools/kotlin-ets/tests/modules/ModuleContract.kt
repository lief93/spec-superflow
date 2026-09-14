package dev.ets

private fun origin(file: String) = SourceSpan(file, 10, 20)
private fun helper(file: String, exported: Boolean = true) = EtsFunction("helper", emptyList(), EtsTypes.NUMBER,
    listOf(EtsReturn(EtsLiteral(7, EtsTypes.NUMBER, origin(file)), origin(file))), origin(file), exported = exported)

fun main() {
    val first = helper("First.kt")
    val second = helper("Second.kt")
    val separate = EtsProgram(listOf(EtsFile("First.kt", listOf(first)), EtsFile("Second.kt", listOf(second))))
    var runtimeCalls = 0
    val runtime = EtsRuntimeSupport { runtimeCalls++; emptyList() }
    val files = emitEtsModules(separate, runtime)
    check(files.size == 2 && files.values.all { "export function helper(" in it })
    check(runtimeCalls == 2)
    check(runCatching { emitEtsProgram(separate, runtime) }.exceptionOrNull() is InvalidTarget)

    fun consumer(callees: List<EtsFunction>): EtsFunction {
        val source = origin("Consumer.kt")
        return EtsFunction("consume", emptyList(), EtsTypes.VOID, callees.map {
            EtsExpressionStatement(EtsCall(EtsReference(it.symbol, source), emptyList(), EtsTypes.NUMBER, source))
        }, source, exported = true)
    }
    fun rejects(program: EtsProgram, message: String) {
        runtimeCalls = 0
        val failure = runCatching { emitEtsModules(program, runtime) }.exceptionOrNull()
        check(failure is InvalidTarget && message in failure.message.orEmpty()) { "Expected $message; got $failure" }
        check(failure.source.file == "Consumer.kt")
        check(runtimeCalls == 0) { "All modules must be planned before selecting runtime support" }
    }
    val hidden = first.copy(exported = false)
    rejects(EtsProgram(listOf(EtsFile("First.kt", listOf(hidden)),
        EtsFile("Consumer.kt", listOf(consumer(listOf(hidden)))))), "not exported")
    rejects(separate.copy(files = separate.files + EtsFile("Consumer.kt", listOf(consumer(listOf(first, second))))),
        "Conflicting module binding")
    val local = helper("Consumer.kt")
    rejects(EtsProgram(listOf(EtsFile("First.kt", listOf(first)),
        EtsFile("Consumer.kt", listOf(local, consumer(listOf(first)))))), "Conflicting module binding")

    val model = EtsClass("Model", emptyList(), origin("Model.kt"), exported = false)
    val parameter = EtsParameter(EtsSymbol("parameter:model", "model", model.symbol.type, origin("Consumer.kt")))
    val signatureOnly = EtsFunction("accept", listOf(parameter), EtsTypes.VOID, emptyList(), origin("Consumer.kt"))
    rejects(EtsProgram(listOf(EtsFile("Model.kt", listOf(model)),
        EtsFile("Consumer.kt", listOf(signatureOnly)))), "not exported")
    val exportedModel = model.copy(exported = true)
    val typed = emitEtsModules(EtsProgram(listOf(EtsFile("Model.kt", listOf(exportedModel)),
        EtsFile("Consumer.kt", listOf(signatureOnly)))), runtime)
    check("import { Model } from \"./Model\";" in typed.getValue("Consumer.ets"))
    val duplicate = EtsProgram(listOf(EtsFile("Consumer.kt", listOf(local, local))))
    rejects(duplicate, "Conflicting target declaration")
    println("PASS per-file names, single-file conflict, value/type exports, import collisions, preflight before runtime")
}
