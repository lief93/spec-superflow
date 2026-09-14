package boundedreceivers

interface Reader<A> { fun read(): A }

open class Base<A>(initial: A) : Reader<A> {
    var current: A = initial
    override fun read(): A = current
    open fun combine(next: A): A = next
}

class IntReader(initial: Int) : Base<Int>(initial) {
    override fun combine(next: Int): Int = read() + next
}

class Wrapped<B>(initial: List<B>) : Base<List<B>>(initial)

interface CounterPort { fun count(): Int }
class Counter(val value: Int) : CounterPort { override fun count(): Int = value }

interface Self<S> { fun self(): S }
class SelfValue(var value: Int) : Self<SelfValue> { override fun self(): SelfValue = this }

class Factory(val receiver: IntReader) {
    var order: Int = 0
    fun get(): IntReader {
        order = order * 10 + 1
        return receiver
    }
    fun argument(): Int {
        order = order * 10 + 2
        return 4
    }
}

fun <T : Reader<Int>> interfaceRead(value: T): Int = value.read()
fun <T : Base<Int>> classRead(value: T, next: Int): Int = value.combine(next)
fun <T : CounterPort> plainRead(value: T): Int = value.count()
fun <A, T : Wrapped<A>> ancestorRead(value: T): A = value.read()[0]
fun <A, U : Reader<A>, T : U> chainedRead(value: T): A = value.read()
fun <T : Self<T>> selfBound(value: T): T = value.self()

fun <T : Reader<Int>> preserve(value: T): T {
    value.read()
    return value
}

fun <T : Base<Int>> ordered(factory: () -> T, argument: () -> Int): Int =
    factory().combine(argument())

fun interfaceCase(seed: Int): Int = interfaceRead(IntReader(seed))
fun classCase(seed: Int): Int = classRead(IntReader(seed), seed + 1)
fun plainCase(seed: Int): Int = plainRead(Counter(seed))
fun ancestorCase(seed: Int): Int = ancestorRead<Int, Wrapped<Int>>(Wrapped(listOf(seed, seed + 1)))
fun chainCase(seed: Int): Int = chainedRead<Int, Reader<Int>, IntReader>(IntReader(seed))

fun identityCase(seed: Int): Boolean {
    val value = IntReader(seed)
    val returned = preserve(value)
    val base: Base<Int> = value
    base.current = seed + 1
    return returned.read() == seed + 1
}

fun selfCase(seed: Int): Boolean {
    val value = SelfValue(seed)
    val returned = selfBound(value)
    value.value = seed + 1
    return returned.value == seed + 1
}

fun orderCase(seed: Int): String {
    val factory = Factory(IntReader(seed))
    val result = ordered({ factory.get() }, { factory.argument() })
    return "${factory.order}|$result"
}
