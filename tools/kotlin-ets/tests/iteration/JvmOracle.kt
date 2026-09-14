package iterationfixture

fun failureText(failure: Throwable): String = failure.javaClass.simpleName +
    (failure.message?.let { ": $it" } ?: "")

fun report(action: () -> Any?) {
    try { println(action()) } catch (failure: Throwable) { println(failureText(failure)) }
}

fun main() {
    report { listValues(emptyList()) }
    report { listValues(listOf(1, -2, 3)) }
    report { iterableValues(mutableListOf(Int.MIN_VALUE, 0, Int.MAX_VALUE)) }
    report { copied(listOf("a", "b")).joinToString(",") }
    report { arrayValues(arrayOf(1, 2, 3)) }
    report { arrayValues(emptyArray()) }
    report { copiedArray(arrayOf("c", "d")).joinToString(",") }
    report { primitiveValues(intArrayOf(Int.MIN_VALUE, Int.MAX_VALUE)) }
    report { constructors(3) }
    report { constructors(Int.MAX_VALUE) }
    report { arrayReplacement(arrayOf(1, 2, 3)) }
    report { arrayReplacement(emptyArray()) }
    report { listCaptures(listOf(-1, 0, 2)) }
    report { listCaptures(emptyList()) }
    report { arrayCaptures(arrayOf(7, 8)) }
    report { nestedJumps(listOf(-1, 0, 1, 2, 3)) }
    report { evaluatedList(listOf(3, 4)) }
    report { evaluatedList(emptyList()) }
    report { sharedCapture(listOf(-1, 2, 3)) }
    report { sharedCapture(listOf(Int.MAX_VALUE, 1)) }
    report { modifiedList(3) }
    report { modificationThenBreak(3) }
    report { iteratorNext(emptyList()) }
    report { iteratorNext(listOf(5)) }
    report { mutableIteratorNext(mutableListOf()) }
    report { mutableIteratorNext(mutableListOf(6)) }
    report { iteratorScenario(emptyList()) }
    report { iteratorScenario(listOf(5)) }
    report { iteratorScenario(listOf(5, 6)) }
    report { progressionNext(Int.MIN_VALUE, Int.MAX_VALUE) }
    report { progressionNext(2, 1) }
    report { composed(-3, 5, 2) }
    report { composed(5, -3, 2) }
    report { composed(Int.MIN_VALUE, Int.MIN_VALUE, 1) }
    report { composed(Int.MIN_VALUE, Int.MAX_VALUE, Int.MAX_VALUE) }
    report { storedProgression(Int.MIN_VALUE, Int.MAX_VALUE, Int.MAX_VALUE) }
    report { storedProgression(Int.MAX_VALUE, Int.MAX_VALUE, 2) }
    report { reversedProgression(9, -2, 3) }
    report { reversedProgression(Int.MAX_VALUE, Int.MIN_VALUE, Int.MAX_VALUE) }
    report { reversedProgression(1, 3, 2) }
    report { repeatedStep(0, 10, 4, 3) }
    report { repeatedStep(0, 10, 4, 0) }
    for (bounds in listOf(intArrayOf(-2, 5, 2), intArrayOf(5, -2, 2), intArrayOf(5, -2, 0),
        intArrayOf(0, Int.MIN_VALUE, 1), intArrayOf(0, Int.MIN_VALUE, -1))) {
        val effects = IterationEffects()
        try { println(evaluatedProgression(effects, bounds[0], bounds[1], bounds[2])) }
        catch (failure: Throwable) { println("${failureText(failure)}|${effects.trace}") }
    }
}
