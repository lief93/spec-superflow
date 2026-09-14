package captureconstruction

open class HeritageBase(val value: Int, touch: () -> Unit) {
    private val `$trace` = value
    init { touch() }
    fun sourceValue(): Int = `$trace`
}

fun capturedHeritage(seed: Int): String {
    var state = seed
    val trace = Trace()
    open class StoredBase : HeritageBase(1, { state += 1; trace.mark("B", state) }) {
        val initial = trace.mark("I", state)
        open fun read(): Int = state
        open fun choose(value: Int = state): Int = value
    }
    class StoredChild(val `$state`: Int) : StoredBase() {
        val after = trace.mark("C", state)
        override fun read(): Int = state + `$state`
        override fun choose(value: Int): Int = value + state
    }
    val child = StoredChild(seed)
    val base: StoredBase = child
    state += 2
    return "${base.read()}:${base.choose()}:${child.initial}:${child.after}:${trace.text}"
}

fun capturedHeritageDispatch(seed: Int): String {
    var state = seed
    val trace = Trace()
    class StoredEntries : HeritageBase {
        val own = trace.mark("I", state)
        constructor(amount: Int = trace.mark("D", state)) : super(amount, { state += 1; trace.mark("A", state) }) {
            trace.mark("X", state)
        }
        constructor(label: String) : super(label.length, { state += 2; trace.mark("B", state) }) {
            trace.mark("Y", state)
        }
        constructor(flag: Boolean) : this(if (flag) "yes" else "n") { state += 3; trace.mark("Z", state) }
        fun read(): Int = state + own + value + sourceValue()
    }
    val first = StoredEntries()
    val second = StoredEntries("ab")
    val third = StoredEntries(true)
    return "${first.read()}:${second.read()}:${third.read()}:$state:${trace.text}"
}
