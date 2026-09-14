package loopfixture

fun ascending(first: Int, last: Int): String {
    var result = ""
    for (value in first..last) {
        result += "$value,"
    }
    return result
}

fun exclusive(first: Int, last: Int): String {
    var result = ""
    for (value in first until last) result += "$value,"
    return result
}

fun descending(first: Int, last: Int): String {
    var result = ""
    for (value in first downTo last) result += "$value,"
    return result
}

fun stepped(first: Int, last: Int, stride: Int): String {
    var result = ""
    for (value in first..last step stride) result += "$value,"
    return result
}

fun descendingStep(first: Int, last: Int, stride: Int): String {
    var result = ""
    for (value in first downTo last step stride) result += "$value,"
    return result
}

class BoundEffects {
    var trace: String = ""
    fun read(label: String, value: Int): Int {
        trace += label
        return value
    }
}

fun evaluated(first: Int, last: Int, stride: Int): String {
    val effects = BoundEffects()
    var result = ""
    for (value in effects.read("F", first)..effects.read("L", last) step effects.read("S", stride)) {
        result += "$value,"
    }
    return "${effects.trace}:$result"
}

fun nestedFlow(first: Int, last: Int): String {
    var result = ""
    outer@ for (left in first..last) {
        for (right in 0..2) {
            if (right == 1) continue
            if (left == 1 && right == 0) continue@outer
            if (left == 2 && right == 2) break@outer
            result += "$left:$right,"
        }
    }
    return result
}

fun capturedIterations(first: Int, last: Int): String {
    val callbacks = mutableListOf<() -> Int>()
    for (value in first..last) {
        if (value == first) {
            callbacks.add { value }
            continue
        }
        callbacks.add { value }
    }
    var result = ""
    for (index in 0 until callbacks.size) result += "${callbacks[index]()},"
    return result
}

fun sharedIterations(first: Int, last: Int): String {
    var total = 0
    val callbacks = mutableListOf<() -> Int>()
    for (value in first..last) {
        fun advance(): Int {
            total += value
            return total
        }
        callbacks.add { advance() }
    }
    var result = ""
    for (index in 0 until callbacks.size) result += "${callbacks[index]()},"
    return "$result:$total"
}

fun nativeLoopClosures(limit: Int): String {
    val callbacks = mutableListOf<() -> Int>()
    var index = 0
    while (index < limit) {
        val captured = index
        callbacks.add { captured }
        index++
    }
    var result = ""
    index = 0
    do {
        if (index >= callbacks.size) break
        result += "${callbacks[index]()},"
        index++
    } while (index < limit)
    return result
}

fun nativeConditionClosure(limit: Int): String {
    var index = 0
    var result = ""
    do {
        result += "$index,"
        index++
    } while (listOf(index).map { item -> item < limit }[0])
    return result
}
