package constructorapi

object Token { val value = 9 }
object WrongObject
object EffectObject

class Amount(val value: Double)
class Wrong
class Effect
class Unclaimed

fun goodEffect() {}
fun badEffect() {}
fun wrongValue(): Int = 0
