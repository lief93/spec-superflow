package constructorfixture

class MultipleRoots {
    val value: Int
    val initialized: Int = Events.mark("I")
    init { Events.mark("J") }
    constructor(value: Int) { this.value = value; Events.mark("N") }
    constructor(value: String) { this.value = value.length; Events.mark("S") }
}

open class DispatchParent(trace: Trace, val value: Int) {
    val initialized: Int = trace.mark("P")
    init { trace.mark("I") }
    constructor(trace: Trace, text: String, extra: Int = trace.mark("D")) : this(trace, text.length + extra) {
        trace.mark("S")
    }
    open fun result(): Int = value
}

class DispatchChild(trace: Trace, text: String) : DispatchParent(trace, text) {
    val child: Int = trace.mark("C")
    override fun result(): Int = value + child
}

abstract class AbstractDispatch {
    val value: Int
    constructor(trace: Trace, value: Int) { trace.mark("A"); this.value = value }
    constructor(trace: Trace, text: String) : this(trace, text.length) { trace.mark("B") }
    abstract fun result(): Int
}

class ConcreteDispatch(trace: Trace, text: String) : AbstractDispatch(trace, text) {
    override fun result(): Int = value + 1
}

open class GenericDispatch<T> {
    val value: T
    var other: T
    constructor(value: T) { this.value = value; other = value }
    constructor(value: T, choose: (T) -> T) { this.value = value; other = choose(value) }
}

class GenericDispatchChild<T>(value: T, choose: (T) -> T) : GenericDispatch<T>(value, choose)

class DispatchDefaults {
    val value: String
    constructor(trace: Trace, first: Int = trace.mark("A"), second: Int = first + trace.mark("B")) {
        value = "$first:$second:${trace.value}"
    }
    constructor(trace: Trace, text: String?) { value = "${text}:${trace.mark("N")}" }
}

open class DispatchBase(val value: Int)

class EarlyDispatch : DispatchBase {
    constructor(trace: Trace, number: Int) : super(number) {
        trace.mark("A")
        if (number > 0) return
        trace.mark("B")
    }
    constructor(trace: Trace, text: String) : super(text.length) { trace.mark("S") }
}

private inline fun <T> constructWithInt(value: Int, factory: (Int) -> T): T = factory(value)

fun dispatchRoots(seed: Int): String {
    Events.text = ""
    val first = constructWithInt(seed, ::MultipleRoots)
    val second = MultipleRoots("text")
    return "${first.value}:${first.initialized}:${second.value}:${second.initialized}:${Events.text}"
}

fun dispatchInheritance(seed: Int): String {
    val trace = Trace()
    val first: DispatchParent = DispatchChild(trace, "text")
    val second = DispatchParent(trace, seed)
    val third = DispatchParent(extra = trace.mark("E"), trace = trace, text = "x")
    val fourth: AbstractDispatch = ConcreteDispatch(trace, "xy")
    return "${first.result()}:${second.result()}:${third.result()}:${fourth.result()}:${trace.value}"
}

fun dispatchGeneric(seed: Int): String {
    val first = GenericDispatch(seed)
    val second = GenericDispatchChild(seed) { it + 1 }
    val third = GenericDispatch("text") { it + "!" }
    return "${first.value}:${second.other}:${third.other}"
}

fun dispatchDefaults(seed: Int): String {
    val trace = Trace()
    val first = DispatchDefaults(trace)
    val second = DispatchDefaults(second = trace.mark("S"), trace = trace, first = trace.mark("F"))
    val third = DispatchDefaults(trace, seed)
    val fourth = DispatchDefaults(trace, null)
    return "${first.value};${second.value};${third.value};${fourth.value}"
}

fun dispatchEarly(seed: Int): String {
    val trace = Trace()
    val first = EarlyDispatch(trace, seed)
    val second = EarlyDispatch(trace, "text")
    return "${first.value}:${second.value}:${trace.value}"
}
