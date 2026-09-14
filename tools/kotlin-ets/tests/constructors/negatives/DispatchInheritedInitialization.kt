open class UnsafeBase(val seed: Int) {
    open val value: Int = seed
    val observed: Int = value
    constructor(seed: String) : this(seed.length)
}
class UnsafeDerived(seed: String) : UnsafeBase(seed) { override val value: Int = 7 }
fun observedDuringConstruction(): Int = UnsafeDerived("text").observed
