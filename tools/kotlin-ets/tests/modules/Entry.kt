package modulefixture

fun describe(value: Int): String = label(bump(Counter(value)).value)

private fun localOffset(value: Int): Int = value + 2
fun entryLocalValue(value: Int): Int = localOffset(value)
