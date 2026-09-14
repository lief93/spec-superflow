interface Reader<out A> { fun read(): A }
fun <T : Reader<Int>> variant(value: T): Int = value.read()
