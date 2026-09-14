package declarationvariance

import Reader
import Marker
import multiple

interface Named { val name: String }
interface Source<T> { fun value(): T }
class NamedValue(private val stored: Specific) : Source<Specific>, Named {
    override val name: String = "named"
    override fun value(): Specific = stored
}
fun <T> both(value: T): String where T : Source<Specific>, T : Named = value.name + ":" + value.value().number
fun <U, T> genericBoth(value: T): U where T : Source<U>, T : Named = value.value()
class BothBox<U, T>(val input: T) where T : Source<U>, T : Named {
    fun value(): U = input.value()
}
interface Self<T> { fun self(): T }
class NamedSelf(val number: Int) : Self<NamedSelf>, Named {
    override val name: String = "self"
    override fun self(): NamedSelf = this
}
fun <T> selfName(value: T): String where T : Self<T>, T : Named = value.self().name
fun <T, U : T> chained(value: U): String where T : Source<Specific>, T : Named = value.name
interface LeftName : Named
interface RightName : Named
class DiamondName(override val name: String) : LeftName, RightName
fun <T> diamondName(value: T): String where T : LeftName, T : RightName = value.name
class OriginalReader(private val number: Int) : Reader, Marker { override fun read(): Int = number }

fun independent(seed: Int): String = both(NamedValue(Specific(seed)))
fun independentGeneric(seed: Int): Int = genericBoth<Specific, NamedValue>(NamedValue(Specific(seed))).number
fun independentClass(seed: Int): Int = BothBox<Specific, NamedValue>(NamedValue(Specific(seed))).value().number
fun independentSelf(seed: Int): String = selfName(NamedSelf(seed))
fun independentChain(seed: Int): String = chained<NamedValue, NamedValue>(NamedValue(Specific(seed)))
fun independentDiamond(seed: Int): String = diamondName(DiamondName("name:" + seed))
fun originalMultiple(seed: Int): Int = multiple(OriginalReader(seed))
