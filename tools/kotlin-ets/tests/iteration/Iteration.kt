package iterationfixture

fun listValues(values: List<Int>): String {
    var result = ""
    for (value in values) result += "$value,"
    return result
}

fun iterableValues(values: Iterable<Int>): String {
    var result = ""
    for (value in values) result += "$value,"
    return result
}

fun <T> copied(values: Iterable<T>): List<T> {
    val result = mutableListOf<T>()
    for (value in values) result.add(value)
    return result
}

fun arrayValues(values: Array<Int>): String {
    var result = ""
    for (value in values) result += "$value,"
    return result
}

fun <T> copiedArray(values: Array<T>): List<T> {
    val result = mutableListOf<T>()
    for (value in values) result.add(value)
    return result
}

fun primitiveValues(values: IntArray): String {
    var result = ""
    for (value in values) result += "$value,"
    return result
}

fun constructors(seed: Int): String =
    "${arrayValues(arrayOf(seed, seed + 1))}:${primitiveValues(intArrayOf(seed, seed + 2))}"

fun arrayReplacement(values: Array<Int>): String {
    var result = ""
    var index = 0
    for (value in values) {
        if (index + 1 < values.size) values[index + 1] = value + 10
        result += "$value,"
        index++
    }
    return result
}

fun listCaptures(values: List<Int>): String {
    val callbacks = mutableListOf<() -> Int>()
    for (value in values) {
        callbacks.add { value }
        if (value == 0) continue
    }
    var result = ""
    for (callback in callbacks) result += "${callback()},"
    return result
}

fun arrayCaptures(values: Array<Int>): String {
    val callbacks = mutableListOf<() -> Int>()
    for (value in values) callbacks.add { value }
    var result = ""
    for (callback in callbacks) result += "${callback()},"
    return result
}

fun nestedJumps(values: Iterable<Int>): String {
    var result = ""
    outer@ for (left in values) {
        for (right in intArrayOf(0, 1, 2)) {
            if (right == 1) continue
            if (left == 0) continue@outer
            if (left == 2 && right == 2) break@outer
            result += "$left:$right,"
        }
    }
    return result
}

class IterationEffects {
    var calls: Int = 0
    var trace: String = ""
    fun values(values: List<Int>): Iterable<Int> {
        calls++
        return values
    }
    fun number(label: String, value: Int): Int {
        trace += label
        return value
    }
}

fun evaluatedList(values: List<Int>): String {
    val effects = IterationEffects()
    var result = ""
    for (value in effects.values(values)) result += "$value,"
    return "${effects.calls}:$result"
}

fun sharedCapture(values: List<Int>): String {
    var total = 0
    val callbacks = mutableListOf<() -> Int>()
    for (value in values) {
        fun add(): Int { total += value; return total }
        callbacks.add { add() }
    }
    var result = ""
    for (callback in callbacks) result += "${callback()},"
    return "$result:$total"
}

fun modifiedList(seed: Int): String {
    val values = mutableListOf(seed, seed + 1)
    var result = ""
    for (value in values) {
        result += "$value,"
        values.add(99)
    }
    return result
}

fun modificationThenBreak(seed: Int): String {
    val values = mutableListOf(seed, seed + 1)
    var result = ""
    for (value in values) {
        result += "$value,"
        values.add(99)
        break
    }
    return "$result:${values.size}"
}

fun iteratorNext(values: List<Int>): Int = values.iterator().next()
fun mutableIteratorNext(values: MutableList<Int>): Int = values.iterator().next()
fun iteratorState(iterator: Iterator<Int>): String = "${iterator.hasNext()}:${iterator.next()}:${iterator.hasNext()}"
fun iteratorScenario(values: List<Int>): String = iteratorState(values.iterator())
fun progressionNext(first: Int, last: Int): Int = (first..last).iterator().nextInt()

fun progressionValues(values: IntProgression): String {
    var result = ""
    for (value in values) result += "$value,"
    return result
}

fun composed(first: Int, last: Int, stride: Int): String {
    var result = ""
    for (value in first until last step stride) result += "$value,"
    return result
}

fun storedProgression(first: Int, last: Int, stride: Int): String {
    val range = first..last
    val progression = range step stride
    return progressionValues(progression)
}

fun reversedProgression(first: Int, last: Int, stride: Int): String {
    val progression = (first downTo last step stride).reversed()
    return progressionValues(progression)
}

fun repeatedStep(first: Int, last: Int, firstStep: Int, nextStep: Int): String {
    val progression = (first until last step firstStep) step nextStep
    return progressionValues(progression)
}

fun evaluatedProgression(effects: IterationEffects, first: Int, last: Int, stride: Int): String {
    var result = ""
    for (value in effects.number("F", first) until effects.number("L", last) step effects.number("S", stride)) {
        result += "$value,"
    }
    return "${effects.trace}:$result"
}
