package modulefixture

fun increment(value: Int): Int = value + 1

private fun localOffset(value: Int): Int = value - 3
fun numbersLocalValue(value: Int): Int = localOffset(value)

fun label(value: Int): String = "value=$value"

fun tail(text: String): String = text.substring(1)

fun bump(counter: Counter): Counter {
    counter.value = increment(counter.value)
    return counter
}
