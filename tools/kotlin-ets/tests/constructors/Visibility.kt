package constructorfixture

open class Guarded protected constructor(val value: Int) {
    protected constructor(value: String, extra: Int = 2) : this(value.length + extra)
    protected var hidden: Int = 3
        private set
    protected open fun offset(extra: Int): Int = value + extra
    fun change(next: Int) { hidden = next }
}

class GuardedChild(seed: Int) : Guarded(seed.toString()) {
    override fun offset(extra: Int): Int = value + extra + 1
    fun evaluate(extra: Int): Int = offset(extra) + hidden
}

open class GuardedRoot protected constructor(val value: Int) {
    protected constructor(value: String) : this(value.length)
    fun make(value: String): GuardedRoot = GuardedRoot(value)
}

class GuardedRootChild(seed: Int) : GuardedRoot(seed)

open class GuardedGeneric<T> protected constructor(val value: T) {
    protected constructor(value: T, unused: Int) : this(value)
    protected fun read(): T = value
}

class GuardedGenericChild<T>(value: T) : GuardedGeneric<T>(value, 1) {
    fun result(): T = read()
}

fun protectedConstruction(seed: Int): String {
    val child = GuardedChild(seed)
    child.change(seed)
    val root = GuardedRootChild(seed)
    val generic = GuardedGenericChild(seed)
    return "${child.value}:${child.evaluate(seed)}:${root.value}:${root.make(seed.toString()).value}:${generic.result()}"
}
