open class BodyBase(val seed: Int) {
    var observed: Int = 0
    constructor(seed: String) : this(seed.length) { observed = read() }
    open fun read(): Int = seed
}
class BodyDerived(seed: String) : BodyBase(seed) {
    val initialized: Int = 7
    override fun read(): Int = initialized
}
fun observedDuringSecondary(): Int = BodyDerived("text").observed
