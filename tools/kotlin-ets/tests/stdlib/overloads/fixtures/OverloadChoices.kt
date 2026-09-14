package stdliboverloads

fun choose(value: Int, trace: MutableList<Int>): Int {
    trace.add(100 + value)
    return 12 / value
}

fun choose(value: Double, trace: MutableList<Int>): Int {
    trace.add(200)
    return 20
}
