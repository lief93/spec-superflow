package constructorfixture

class Trace {
    var value: String = ""
    fun mark(label: String): Int {
        value += label
        return value.length
    }
}

class Chain(val trace: Trace, val number: Int) {
    var marker: Int = 0
    private var extra: Int = trace.mark("P")
    init { trace.mark("I") }
    constructor(trace: Trace, label: String, count: Int = trace.mark("D")) : this(trace, count) {
        extra += trace.mark(label)
    }
    constructor(trace: Trace) : this(trace, "S") {
        trace.mark("T")
        if (number > 0) return
        trace.mark("X")
    }
    fun result(): String = "$number:$extra:${trace.value}"
    fun self(): Chain = this
    fun new_Chain(): Int = 9
}

class Box<T>(val value: T, var other: T) {
    constructor(value: T, choose: (T) -> T) : this(value, choose(value)) {
        other = choose(other)
    }
    constructor(value: T) : this(value, { it })
    fun result(): T = other
}

open class Base(val number: Int) {
    open fun result(extra: Int = 2): Int = number + extra
}

class Derived(number: Int) : Base(number) {
    constructor(trace: Trace, value: Int = trace.mark("D")) : this(value) { trace.mark("S") }
    override fun result(extra: Int): Int = number - extra
}

class Captured(val number: Int) {
    var read: () -> Int = { number }
    constructor(trace: Trace, number: Int) : this(number) {
        var calls = 0
        read = { calls += 1; trace.mark("C"); this.number + calls }
    }
}

class Defaults private constructor(val value: String) {
    constructor(trace: Trace, first: Int = trace.mark("A"), second: Int = first + trace.mark("B")) :
        this("$first:$second:${trace.value}")
}

class Failing(val trace: Trace, val number: Int) {
    init { trace.mark("P") }
    constructor(trace: Trace, divisor: Int, label: String) : this(trace, trace.mark("A") / divisor) {
        trace.mark(label)
    }
}

class Secret private constructor(val value: Int) {
    private constructor(trace: Trace, value: Int) : this(value + 1) { trace.mark("S") }
    constructor(trace: Trace) : this(trace, trace.mark("D"))
    private fun adjusted(delta: Int): Int = value + delta
    fun result(delta: Int): Int = adjusted(delta)
}

class ReferenceConstructed(val number: Int = 0) {
    constructor() : this(7)
}

inline fun <T> createReference(factory: () -> T): T = factory()
