package portablecommon

fun <T> newList(): MutableList<T> = mutableListOf()
fun <T> append(values: MutableList<T>, value: T): Boolean = values.add(value)
fun exhausted(): Nothing = throw NoSuchElementException()
