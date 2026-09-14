package genericheritage

interface Value<T> {
    fun read(): T
    fun replace(next: T): T
}

open class Storage<T>(initial: T) : Value<T> {
    var current: T = initial
    override fun read(): T = current
    override fun replace(next: T): T {
        val previous = current
        current = next
        return previous
    }
}

open class Forward<U>(input: U) : Storage<U>(input)

class IntStore(input: Int) : Forward<Int>(input) {
    override fun replace(next: Int): Int = read() + next
}

class Nested<V>(input: List<V>) : Storage<List<V>>(input)

interface View<U> : Value<U>

class TextValue(val text: String) : View<String> {
    override fun read(): String = text
    override fun replace(next: String): String = text + next
}

abstract class AbstractValue<T> : Value<T> {
    abstract override fun read(): T
    override fun replace(next: T): T = next
}

class ConcreteText(val text: String) : AbstractValue<String>() {
    override fun read(): String = text
}

interface Left<T> : Value<T>
interface Right<T> : Value<T>
interface Both<T> : Left<T>, Right<T>

class DiamondText(val text: String) : Both<String> {
    override fun read(): String = text
    override fun replace(next: String): String = next + text
}

class Trace {
    var count: Int = 0
    fun mark(value: Int): Int {
        count += 1
        return value + 1
    }
}

class EffectChild(input: Int, trace: Trace) : Forward<Int>(trace.mark(input))

// Exact former UnsupportedGeneric.kt hierarchy, now exercised through its base type.
open class GenericBase<T>(val value: T)
class GenericChild : GenericBase<Int>(3)

fun migratedGeneric(): Int {
    val base: GenericBase<Int> = GenericChild()
    return base.value
}

fun genericDispatch(seed: Int): String {
    val child = IntStore(seed)
    val base: Storage<Int> = child
    val contract: Value<Int> = child
    return "${child.read()}|${base.replace(seed + 2)}|${contract.replace(seed - 1)}"
}

fun parameterized(seed: Int): Int {
    val child = Forward(seed)
    val contract: Value<Int> = child
    val previous = contract.replace(seed + 1)
    return previous + child.read()
}

fun nestedArguments(seed: Int): Int {
    val contract: Value<List<Int>> = Nested(listOf(seed, seed + 1))
    val first = contract.read()[0]
    val previous = contract.replace(listOf(seed - 1))
    return first + previous[1]
}

fun stringDispatch(seed: Int): String {
    val view: View<String> = TextValue("v$seed")
    val abstract: AbstractValue<String> = ConcreteText("a$seed")
    val diamond: Both<String> = DiamondText("d$seed")
    return view.replace("!") + abstract.read() + diamond.replace("?")
}

fun constructorEffects(seed: Int): String {
    val trace = Trace()
    val value: Value<Int> = EffectChild(trace.mark(seed), trace)
    return "${trace.count}|${value.read()}"
}

fun <T> throughInterface(value: Value<T>, next: T): T = value.replace(next)

fun genericCaller(seed: Int): Int {
    val value = Forward(seed)
    return throughInterface(value, seed + 3) + value.read()
}
