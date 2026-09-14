package binaryapplication

import binarylibrary.binaryTransform

class Trace(var value: Int) {
    var events: String = ""
    fun next(label: String): Int {
        events += label
        value += 1
        return value
    }
}

fun binaryScenario(start: Int): String {
    val trace = Trace(start)
    var captured = 3
    val result = binaryTransform(second = trace.next("B"), first = trace.next("A")) { a, b ->
        trace.events += "L"
        captured += a
        a * 10 + b + captured
    }
    val defaulted = binaryTransform(trace.next("D")) { a, b ->
        captured += 1
        a + b
    }
    return "$result:$defaulted:$captured:${trace.value}:${trace.events}"
}
