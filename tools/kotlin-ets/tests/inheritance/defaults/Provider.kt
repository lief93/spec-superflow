package defaultfixture

class Effects {
    var trace: String = ""
    fun number(label: String, value: Int): Int { trace += label; return value }
    fun receiver(value: DefaultBase): DefaultBase { trace += "R"; return value }
}

private fun adjustment(value: Int): Int = value + 1

fun `DefaultBase_calculate$default`(value: Int): Int = value

open class DefaultBase(val effects: Effects, val initial: Int) {
    open fun seed(): Int = effects.number("B", initial)
    open fun calculate(left: Int = seed(), right: Int = effects.number("D", adjustment(left))): Int = left - right
    open fun apply(value: Int, action: (Int) -> Int = { it + value }): Int = action(value)
    open fun <T> choose(value: T, fallback: T = value): T = fallback
    fun finalValue(value: Int = seed()): Int = value
}

class DefaultChild(effects: Effects, initial: Int) : DefaultBase(effects, initial) {
    override fun seed(): Int = effects.number("S", initial + 2)
    override fun calculate(left: Int, right: Int): Int = effects.number("C", left + right)
    override fun apply(value: Int, action: (Int) -> Int): Int = action(value) + 1
    override fun <T> choose(value: T, fallback: T): T = fallback
}

interface GenericDefaults<T> {
    fun seed(): T
    fun choose(value: T = seed(), fallback: T = value): T
}
class StringDefaults : GenericDefaults<String> {
    override fun seed(): String = "seed"
    override fun choose(value: String, fallback: String): String = fallback + "!"
}

abstract class AbstractDefaults {
    abstract fun calculate(value: Int = 9): Int
}
class ConcreteDefaults : AbstractDefaults() {
    override fun calculate(value: Int): Int = value + 1
}

open class RecursiveDefaults {
    var remaining: Int = 3
    fun next(): Int { remaining -= 1; return if (remaining > 0) calculate() else 1 }
    open fun calculate(value: Int = next()): Int = value + 1
}
class RecursiveChild : RecursiveDefaults() {
    override fun calculate(value: Int): Int = value + 2
}

open class NullableDefaults {
    open fun optional(value: String? = "default"): String? = value
}
class NullableChild : NullableDefaults()

open class WideDefaults {
    open fun sum(
        p0: Int = 1, p1: Int = 2, p2: Int = 3, p3: Int = 4,
        p4: Int = 5, p5: Int = 6, p6: Int = 7, p7: Int = 8,
        p8: Int = 9, p9: Int = 10, p10: Int = 11, p11: Int = 12,
        p12: Int = 13, p13: Int = 14, p14: Int = 15, p15: Int = 16,
        p16: Int = 17, p17: Int = 18, p18: Int = 19, p19: Int = 20,
        p20: Int = 21, p21: Int = 22, p22: Int = 23, p23: Int = 24,
        p24: Int = 25, p25: Int = 26, p26: Int = 27, p27: Int = 28,
        p28: Int = 29, p29: Int = 30, p30: Int = 31,
        p31: Int = p30 + 1, p32: Int = p31 + 1, p33: Int = p32 + 1
    ): Int = p0 + p30 + p31 + p32 + p33
}
class WideChild : WideDefaults()

open class GenericBase<T>(val initial: T) {
    open fun choose(value: T = initial): T = value
}
open class GenericMiddle<T>(initial: T) : GenericBase<T>(initial)
class GenericChild(initial: String) : GenericMiddle<String>(initial) {
    override fun choose(value: String): String = value + "!"
}
