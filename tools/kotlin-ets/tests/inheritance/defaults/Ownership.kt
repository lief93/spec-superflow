package defaultfixture

open class RestrictedBase<T>(private val value: T, protected val effects: Effects) {
    protected open fun choose(first: T = value, second: T = first): T {
        effects.number("B", 1)
        return second
    }
    private fun seed(count: Int = effects.number("P", 2)): Int = count + 1
    fun privateDefault(): Int = seed()
    open fun publish(value: T = this.value): T = value
}

class RestrictedChild<T>(value: T, effects: Effects) : RestrictedBase<T>(value, effects) {
    public override fun choose(first: T, second: T): T {
        effects.number("C", 1)
        return second
    }
    fun inherited(): T = choose()
}

fun ownedDefaults(seed: Int): String {
    val effects = Effects()
    val child = RestrictedChild(seed, effects)
    val inside = child.inherited()
    val outside = child.choose()
    val provided = child.choose(second = seed + 1)
    val privateValue = child.privateDefault()
    val published = child.publish()
    return "$inside:$outside:$provided:$privateValue:$published:${effects.trace}"
}
