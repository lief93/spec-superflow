package overloadconsumer

import overloadbinary.select

class Trace(var calls: Int, var text: String) {
    fun intArg(value: Int): Int {
        calls += 1
        text += "I"
        return value
    }
    fun doubleArg(value: Double): Double {
        calls += 1
        text += "D"
        return value
    }
    fun bias(value: Int): Int {
        calls += 1
        text += "B"
        return value
    }
}

fun scenario(seed: Int): String {
    val trace = Trace(0, "")
    val integer = select(trace.intArg(seed)) { value ->
        trace.text += "i"
        value * 2
    }
    val decimal = select(value = trace.doubleArg(seed.toDouble()), bias = trace.bias(7)) { value ->
        trace.text += "d"
        if (value > 0.0) 4 else 6
    }
    val named = select(bias = trace.bias(9), value = trace.intArg(seed + 1)) { value ->
        trace.text += "n"
        value + 1
    }
    val defaultDouble = select(trace.doubleArg(seed.toDouble())) { value ->
        trace.text += "e"
        if (value > 0.0) 2 else 4
    }
    return "$integer/$decimal/$named/$defaultDouble/${trace.calls}/${trace.text}"
}
