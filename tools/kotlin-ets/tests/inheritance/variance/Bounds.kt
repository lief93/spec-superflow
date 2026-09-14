package declarationvariance

interface SpecificSource : Producer<Specific>
class FixedSource(private val value: Specific) : SpecificSource {
    override fun read(): Specific = value
}
fun <T> broadFirst(source: T): Int where T : Producer<Specific>, T : SpecificSource = source.read().number
fun <T> narrowFirst(source: T): Int where T : SpecificSource, T : Producer<Specific> = source.read().number
class BoundedBox<T>(val source: T) where T : Producer<Specific>, T : SpecificSource {
    fun read(): Int = source.read().number
}
fun <T> valueBounds(value: T): Int where T : Producer<Specific>, T : FixedSource = value.read().number
fun broadBound(seed: Int): Int = broadFirst(FixedSource(Specific(seed)))
fun narrowBound(seed: Int): Int = narrowFirst(FixedSource(Specific(seed)))
fun classBound(seed: Int): Int = BoundedBox(FixedSource(Specific(seed))).read()
fun nominalBound(seed: Int): Int = valueBounds(FixedSource(Specific(seed)))
