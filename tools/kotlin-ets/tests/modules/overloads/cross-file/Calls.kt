package crossfileoverloads

fun crossFileCase(seed: Int): String {
    val trace = Trace()
    val choose_1 = seed
    val integer = choose(suffix = trace.mark("S", seed + 1), value = trace.mark("I", seed))
    val decimal = choose(suffix = trace.mark("T", seed + 2), value = trace.markDouble("D", seed.toDouble()))
    return "$integer|$decimal|${forward(seed)}|${uniqueName(seed)}|${choose_0(choose_1)}|${trace.value}"
}

fun identityCase(seed: Int): String {
    val original = Token(seed)
    val returned = keep(original)
    returned.value += 1
    return "${original.value}|${keep(seed)}"
}
