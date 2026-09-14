package privateoverloads

private fun pick(value: Int): Int = value + 1000

fun unrelatedPrivateCase(value: Int): String = "${pick(value)}:${pick(value.toDouble())}"
