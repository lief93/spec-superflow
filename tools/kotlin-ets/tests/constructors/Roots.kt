package constructorfixture

object Events {
    var text: String = ""
    fun mark(label: String): Int { text += label; return text.length }
}

class NativeRoot {
    val seed: Int
    val stamp: Int = Events.mark("P")
    init { Events.mark("I") }
    constructor(seed: Int) {
        this.seed = seed
        Events.mark("R")
        if (seed < 0) return
        Events.mark("N")
    }
    constructor(seed: Int, label: String) : this(seed) { Events.mark(label) }
    constructor(label: String) : this(Events.mark(label)) { Events.mark("S") }
    constructor() : this("D") { Events.mark("T") }
}

class GenericNative<T> {
    val value: T
    var other: T
    constructor(value: T) { this.value = value; other = value; Events.mark("G") }
    constructor(value: T, choose: (T) -> T) : this(choose(value)) {
        other = choose(other)
        Events.mark("F")
    }
}

open class RootBase {
    val number: Int
    constructor(trace: Trace, seed: Int) { number = seed; trace.mark("B") }
    open fun result(extra: Int = 3): Int = number + extra
}

class RootChild : RootBase {
    val own: Int
    constructor(trace: Trace, seed: Int) : super(trace, trace.mark("A") + seed) {
        own = seed
        trace.mark("C")
    }
    constructor(trace: Trace) : this(trace, trace.mark("D")) { trace.mark("E") }
    override fun result(extra: Int): Int = number + own + extra
}

abstract class AbstractNative {
    val value: Int
    constructor(value: Int) { this.value = value }
    abstract fun read(): Int
}

class ConcreteNative(value: Int) : AbstractNative(value) {
    override fun read(): Int = value
}

class Closed {
    val value: Int
    private constructor(value: Int) { this.value = value }
    constructor(trace: Trace) : this(trace.mark("K")) { trace.mark("L") }
}
