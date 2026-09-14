package constructorfixture

fun construct(seed: Int): String {
    val trace = Trace()
    val first = Chain(trace)
    val second = Chain(trace, "E", seed)
    val third = Chain(trace, "N")
    first.self().marker = seed
    return first.result() + ";" + second.result() + ";" + third.result() + ";${first.marker}:${second.marker}"
}

fun generic(seed: Int): String {
    val first = Box(seed) { it + 1 }
    val second = Box("hello")
    return "${first.value}:${first.result()}:${second.result()}"
}

fun inherited(seed: Int): String {
    val trace = Trace()
    val first: Base = Derived(trace)
    val second: Base = Derived(trace, seed)
    return "${first.result()}:${second.result()}:${trace.value}"
}

fun captured(seed: Int): String {
    val trace = Trace()
    val instance = Captured(trace, seed)
    return "${instance.read()}:${instance.read()}:${trace.value}"
}

fun defaults(seed: Int): String {
    val trace = Trace()
    val first = Defaults(trace)
    val second = Defaults(second = trace.mark("S"), trace = trace, first = trace.mark("F"))
    val third = Defaults(trace, seed)
    return "${first.value};${second.value};${third.value}"
}

fun failure(trace: Trace, seed: Int): Failing = Failing(trace, seed, "S")

fun privateChain(seed: Int): String {
    val trace = Trace()
    val value = Secret(trace)
    return "${value.result(seed)}:${trace.value}"
}

fun reference(seed: Int): Int = createReference(::ReferenceConstructed).number + seed

fun nativeRoot(seed: Int): String {
    Events.text = ""
    val first = NativeRoot(seed, "Q")
    val second = NativeRoot()
    val legacy = NoPrimary(seed)
    return "${first.seed}:${first.stamp}:${second.seed}:${second.stamp}:${legacy.value}:${Events.text}"
}

fun genericRoot(seed: Int): String {
    Events.text = ""
    val first = GenericNative(seed) { Events.mark("C"); it + 1 }
    val second = GenericNative("text")
    return "${first.value}:${first.other}:${second.value}:${Events.text}"
}

fun inheritedRoot(seed: Int): String {
    val trace = Trace()
    val first: RootBase = RootChild(trace, seed)
    val second: RootBase = RootChild(trace)
    val third: AbstractNative = ConcreteNative(seed)
    return "${first.result()}:${second.result()}:${third.read()}:${trace.value}"
}

fun privateRoot(seed: Int): String {
    val trace = Trace()
    val value = Closed(trace)
    return "${value.value + seed}:${trace.value}"
}
