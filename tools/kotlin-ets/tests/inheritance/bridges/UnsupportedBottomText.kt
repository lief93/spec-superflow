fun <T> identity(value: T): T = value
fun bottomText(): String = "${identity(null)}"
