interface Reader { fun read(): Int }
fun <T : Reader?> nullable(value: T): Int = value?.read() ?: 0
