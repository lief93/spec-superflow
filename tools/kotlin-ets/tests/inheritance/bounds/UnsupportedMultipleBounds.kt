interface Reader { fun read(): Int }
interface Marker
fun <T> multiple(value: T): Int where T : Reader, T : Marker = value.read()
