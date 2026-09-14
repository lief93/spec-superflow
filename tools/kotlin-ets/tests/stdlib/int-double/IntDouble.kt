package intdouble

fun widen(value: Int, trace: MutableList<Int>): Double {
    trace.add(value)
    return value.toDouble()
}

fun conversionReceiver(value: Int, trace: MutableList<Int>): Int {
    trace.add(7)
    return 12 / value
}

fun receiverOnce(value: Int, trace: MutableList<Int>): Double = conversionReceiver(value, trace).toDouble()
