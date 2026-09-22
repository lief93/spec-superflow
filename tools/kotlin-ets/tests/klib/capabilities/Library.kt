package dependencies

inline fun <T> twice(value: T, transform: (T) -> T): T = transform(transform(value))
fun adjusted(value: Int): Int = twice(value) { it + 1 }
