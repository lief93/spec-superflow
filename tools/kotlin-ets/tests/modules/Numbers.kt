package modulefixture

internal fun increment(value: Int): Int = value + 1

private fun localOffset(value: Int): Int = value - 3
fun numbersLocalValue(value: Int): Int = localOffset(value)

internal inline fun inlineLocalValue(value: Int): Int = localOffset(value)

private fun <T> identity(value: T): T = value
internal inline fun <T> inlineIdentity(value: T): T = identity(value)

private fun withDefault(value: Int, extra: Int = value + 3): Int = value - extra
internal inline fun inlineDefault(value: Int): Int = withDefault(value)

private fun hidden(value: Int): Int = value + 1
private fun hidden(value: Double): Int = 2
private fun `access$hidden$tNumbersKt`(value: String): String = value
internal inline fun inlineOverloaded(value: Int): Int = hidden(value) + hidden(1.0)

fun label(value: Int): String = "value=$value"

fun tail(text: String): String = text.substring(1)

internal fun bump(counter: Counter): Counter {
    counter.value = increment(counter.value)
    return counter
}
