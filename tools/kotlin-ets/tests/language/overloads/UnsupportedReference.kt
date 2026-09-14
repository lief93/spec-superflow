fun select(value: Int): Int = value
fun select(value: String): String = value
fun reference(): (Int) -> Int = ::select
