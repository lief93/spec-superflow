package inlinefixture

import inlinelibrary.chooseNonNegative
import inlinelibrary.libraryTransform

class Trace(var value: Int) {
    var events: String = ""
    fun next(label: String): Int {
        events += label
        value += 1
        return value
    }
}

fun inlineSourceScenario(start: Int): String {
    val trace = Trace(start)
    var captured = 3
    val result = libraryTransform(second = trace.next("B"), first = trace.next("A")) { a, b ->
        trace.events += "L"
        captured += a
        a * 10 + b + captured
    }
    val defaulted = libraryTransform(trace.next("D")) { a, b ->
        captured += 1
        a + b
    }
    val branched = chooseNonNegative(-trace.value) { value ->
        trace.events += "E"
        value + captured
    }
    return "$result:$defaulted:$branched:$captured:${trace.value}:${trace.events}"
}

fun crossFileScenario(base: Int): Int {
    var calls = 0
    val result = localTwice(base) { value ->
        calls += 1
        value + calls
    }
    return result * 10 + calls
}
