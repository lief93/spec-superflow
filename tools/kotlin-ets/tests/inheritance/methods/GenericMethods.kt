package genericmethods

class Cell(var value: Int)

interface Mapper<C> {
    fun <M> select(context: C, value: M): M
    fun <M> convert(value: M, transform: (M) -> C): C
}

open class MethodBase<A>(val stored: A) : Mapper<A> {
    override fun <B> select(context: A, value: B): B = value
    override fun <B> convert(value: B, transform: (B) -> A): A = transform(value)
    open fun <B> keep(value: B): B = value
}

open class MethodMiddle<D>(initial: D) : MethodBase<D>(initial)
class MethodLeaf(initial: Int) : MethodMiddle<Int>(initial) {
    override fun <E> select(context: Int, value: E): E = value
    override fun <E> convert(value: E, transform: (E) -> Int): Int = transform(value) + 1
}

interface Constrained<C> {
    fun <M : C> bounded(value: M): M
    fun <M : C, N : M> chained(value: N): N
}

class Constraints<A> : Constrained<A> {
    override fun <B : A> bounded(value: B): B = value
    override fun <B : A, D : B> chained(value: D): D = value
}

fun <R : Mapper<Int>, V> throughBound(receiver: R, value: V): V = receiver.select(7, value)

class Effects(var trace: String, var calls: Int) {
    fun receiver(): Mapper<Int> {
        trace = trace + "R"
        calls = calls + 1
        return MethodLeaf(3)
    }
    fun argument(seed: Int): Int {
        trace = trace + "A"
        calls = calls + 1
        return seed
    }
    fun callback(): (Int) -> Int {
        trace = trace + "C"
        calls = calls + 1
        return { value ->
            trace = trace + "I"
            calls = calls + 1
            value + 2
        }
    }
}

fun interfaceCase(seed: Int): String {
    val direct = MethodLeaf(seed)
    val view: Mapper<Int> = direct
    return "${direct.select<Int>(seed, seed + 1)}/${view.select(seed, "interface")}/${view.convert(seed) { it + 2 }}"
}

fun inheritedCase(seed: Int): String {
    val leaf = MethodLeaf(seed)
    val middle: MethodMiddle<Int> = leaf
    val base: MethodBase<Int> = leaf
    return "${leaf.keep(seed)}/${middle.keep("inherited")}/${base.convert(seed) { it + 3 }}"
}

fun substitutionsCase(seed: Int): String {
    val numbers = MethodBase<Int>(seed)
    val text: Mapper<String> = MethodBase<String>("stored")
    return "${numbers.convert("abc") { it.length + seed }}/${text.convert(seed) { "n$it" }}/${text.select("context", seed)}"
}

fun constraintsCase(seed: Int): String {
    val methods: Constrained<Cell> = Constraints<Cell>()
    val original = Cell(seed)
    val alias = methods.bounded(original)
    val chained = methods.chained<Cell, Cell>(original)
    original.value = original.value + 4
    return "${alias.value}/${chained.value}"
}

fun boundedCase(seed: Int): String {
    val method = MethodLeaf(seed)
    val original = Cell(seed)
    val alias = throughBound(method, original)
    original.value = original.value + 5
    return "${throughBound(method, seed)}/${alias.value}"
}

fun effectsCase(seed: Int): String {
    val effects = Effects("", 0)
    val result = effects.receiver().convert(effects.argument(seed), effects.callback())
    return "$result/${effects.trace}/${effects.calls}"
}
