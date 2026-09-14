package genericfixture

fun <T> identity(value: T): T = value
fun <T> choose(value: T, fallback: T = value): T = fallback
fun <T, R> transform(value: T, action: (T) -> R): R = action(value)
fun <T> first(values: List<T>): T = values[0]
fun <T> nullable(value: T?): T? = value
fun <T> recursive(value: T, depth: Int): T = if (depth == 0) value else recursive(value, depth - 1)
fun <T> Box<T>.unbox(): T = value
fun <T : Any> nonNull(value: T): T = value

fun functionCases(seed: Int): String {
    val number = identity(seed)
    val text = identity("value")
    val selected = choose(seed)
    val changed = choose(seed, seed + 1)
    val result = transform(seed) { it + 2 }
    val head = first(listOf(seed, seed + 3))
    val absent = nullable<String>(null)
    val present = nullable("present")
    return "$number:$text:$selected:$changed:$result:$head:$absent:$present:${recursive(seed, 3)}:${nonNull(seed)}"
}
