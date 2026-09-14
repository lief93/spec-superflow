package invalidindependent

interface Reader { fun read(): Int }
interface Marker
class OnlyReader : Reader { override fun read(): Int = 1 }
fun <T> constrained(value: T): Int where T : Reader, T : Marker = value.read()
fun missingBound(): Int = constrained(OnlyReader())
