package captureconstruction

class Trace {
    var text = ""
    fun mark(label: String, value: Int): Int { text += label; return value }
}

fun localChain(seed: Int): String {
    var state = seed
    val trace = Trace()
    class Counter private constructor(val step: Int) {
        init { trace.mark("I", step) }
        constructor(label: String, step: Int = trace.mark("D", 2)) : this(trace.mark("A", step)) {
            trace.mark(label, step)
            state += step
        }
        constructor() : this("B") { trace.mark("C", 0) }
        fun read(): Int = state + step
    }
    val first = Counter()
    val second = Counter("E", trace.mark("F", 3))
    return "${first.read()}:${second.read()}:$state:${trace.text}"
}

fun localRoot(seed: Int): String {
    val trace = Trace()
    class Local {
        val value: Int
        constructor(amount: Int) { value = trace.mark("R", seed + amount) }
        constructor() : this(trace.mark("A", 2)) { trace.mark("B", 0) }
        fun read(): Int = value + seed
    }
    val first = Local()
    val second = Local(4)
    return "${first.read()}:${second.read()}:${trace.text}"
}

fun collision(seed: Int): String {
    class Collision(val `$seed`: Int, val `$seed_0`: Int) {
        constructor(label: String, `$seed`: Int) : this(`$seed`, label.length)
        fun read(): Int = seed + `$seed` + `$seed_0`
    }
    return "${Collision("abc", seed + 1).read()}"
}

fun localDispatch(seed: Int): String {
    val trace = Trace()
    class Entries {
        val value: Int
        constructor(amount: Int = trace.mark("D", seed)) { value = trace.mark("A", amount) }
        constructor(text: String) { value = trace.mark("B", text.length) + seed }
    }
    val first = Entries()
    val second = Entries("abc")
    return "${first.value}:${second.value}:${trace.text}"
}

fun localPersistent(seed: Int): String {
    var state = seed
    val trace = Trace()
    class Persistent {
        val value: Int
        init { trace.mark("I", state) }
        constructor(value: Int = trace.mark("D", state)) { this.value = trace.mark("A", value); state += 1 }
        constructor(value: String) { this.value = trace.mark("B", value.length); state += 2 }
        constructor(flag: Boolean) : this(if (flag) "xy" else "z") { state += 3 }
        fun read(): Int = value + state
    }
    val first = Persistent(value = seed)
    val second = Persistent("abc")
    val third = Persistent(true)
    val fourth = Persistent()
    return "${first.read()}:${second.read()}:${third.read()}:${fourth.read()}:${trace.text}"
}

class Outer(var seed: Int, val trace: Trace) {
    inner class Multi {
        val value: Int
        init { trace.mark("I", seed) }
        constructor(value: Int = trace.mark("D", seed)) { this.value = trace.mark("A", value) }
        constructor(value: String) { this.value = trace.mark("B", value.length) }
        constructor(flag: Boolean) : this(if (flag) "abc" else "x") { trace.mark("C", 0) }
        fun read(): Int = value + seed
        inner class Leaf {
            val extra: Int
            constructor(extra: Int) { this.extra = extra }
            constructor(extra: String) { this.extra = extra.length }
            fun read(): Int = value + seed + extra
        }
    }
    inner class Item(val amount: Int) {
        init { trace.mark("I", amount) }
        constructor(label: String, amount: Int = trace.mark("D", seed)) : this(trace.mark("A", amount)) {
            trace.mark(label, amount)
        }
        constructor() : this("B") { trace.mark("C", 0) }
        fun read(): Int = seed + amount
    }
    inner class Root {
        val amount: Int
        constructor(value: Int) { amount = trace.mark("R", value) }
        constructor() : this(trace.mark("A", seed)) { trace.mark("B", 0) }
        fun read(): Int = seed + amount
    }
}

fun innerChain(seed: Int): String {
    val trace = Trace()
    val outer = Outer(seed, trace)
    val other = Outer(seed + 10, trace)
    val first = outer.Item()
    val second = other.Item("E", trace.mark("F", 3))
    outer.seed += 1
    return "${first.read()}:${second.read()}:${trace.text}"
}

fun innerRoot(seed: Int): String {
    val trace = Trace()
    val outer = Outer(seed, trace)
    val first = outer.Root()
    val second = outer.Root(4)
    outer.seed += 1
    return "${first.read()}:${second.read()}:${trace.text}"
}

fun innerDispatch(seed: Int): String {
    val trace = Trace()
    val outer = Outer(seed, trace)
    val other = Outer(seed + 10, trace)
    fun receiver(): Outer { trace.mark("R", 0); return outer }
    val first = receiver().Multi()
    val second = other.Multi(true)
    val leaf = first.Leaf("abc")
    val otherLeaf = second.Leaf(5)
    outer.seed += 1
    return "${first.read()}:${second.read()}:${leaf.read()}:${otherLeaf.read()}:${trace.text}"
}

object Journal {
    var text = ""
    fun mark(label: String, value: Int): Int { text += label; return value }
}

class Initializer {
    var total = 0
    init {
        val offset = Journal.mark("I", 5)
        class Stamp { fun read(): Int = offset }
        total = Stamp().read()
    }
    constructor(value: Int) { total += Journal.mark("A", value) }
    constructor(value: String) { total += Journal.mark("B", value.length) }
}

fun initializer(seed: Int): String {
    Journal.text = ""
    val first = Initializer(seed)
    val second = Initializer("abc")
    return "${first.total}:${second.total}:${Journal.text}"
}
