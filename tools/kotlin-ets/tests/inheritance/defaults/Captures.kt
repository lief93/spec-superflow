package defaultfixture

fun localCapturedDefaults(seed: Int): String {
    var state = seed
    val effects = Effects()
    open class CapturedBase {
        open fun calculate(value: Int = effects.number("D", state)): Int = value
        open fun apply(value: Int, action: (Int) -> Int = { it + state }): Int = action(value)
    }
    class CapturedChild(val `$state`: Int) : CapturedBase() {
        override fun calculate(value: Int): Int = value + value + `$state`
        override fun apply(value: Int, action: (Int) -> Int): Int = action(value) + 1
    }
    fun receiver(value: CapturedBase): CapturedBase {
        effects.trace += "R"
        return value
    }
    val child = CapturedChild(seed)
    val base: CapturedBase = child
    val first = receiver(base).calculate()
    state += 1
    val second = child.calculate()
    val third = base.apply(seed)
    val explicit = child.calculate(effects.number("E", seed))
    return "$first:$second:$third:$explicit:${effects.trace}"
}

class CapturedOuter(var seed: Int, val effects: Effects) {
    inner open class CapturedInner {
        open fun calculate(value: Int = effects.number("D", seed)): Int = value
        open fun apply(value: Int, action: (Int) -> Int = { it + seed }): Int = action(value)
    }
}

fun innerCapturedDefaults(seed: Int): String {
    val effects = Effects()
    val outer = CapturedOuter(seed, effects)
    val other = CapturedOuter(seed + 3, effects)
    val first = outer.CapturedInner()
    val second = other.CapturedInner()
    val before = first.calculate()
    outer.seed += 1
    val after = first.calculate()
    val separate = second.calculate()
    return "$before:$after:$separate:${first.apply(seed)}:${effects.trace}"
}
