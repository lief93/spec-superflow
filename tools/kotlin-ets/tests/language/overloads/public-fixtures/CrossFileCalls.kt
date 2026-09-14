package overloadfixture

fun crossFileCase(seed: Int): String {
    val receiver = FinalMethods(0, seed)
    val first = receiver.choose(seed)
    val second = receiver.choose(1.0)
    val generic = GenericMethods<Int>()
    return pick(seed) + "/" + pick(1.0) + "/" + pick("cross") + "/" +
        first + "/" + second + "/" + receiver.calls + "/" +
        selected(seed) + "/" + forward(seed) + "/" +
        genericForward(generic, seed, "cross")
}
