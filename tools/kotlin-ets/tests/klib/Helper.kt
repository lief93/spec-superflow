package klibhelper

fun <T> echo(value: T): T = value
fun offset(value: Int): Int = value + 2
fun bias(value: Int, amount: Int = 5): Int = value + amount
