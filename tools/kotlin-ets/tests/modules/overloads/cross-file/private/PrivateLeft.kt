package privateoverloads

private fun localOffset(value: Int): Int = value + 1
private fun privateOrPublic(value: Int): Int = value + 2
private fun pick(value: Int): Int = value + 100
private fun mixed(value: Int): Int = value + 3
fun mixed(value: Double): Int = if (value > 0.0) 40 else 50

fun leftPrivateCase(value: Int): String =
    "${localOffset(value)}:${privateOrPublic(value)}:${mixed(value)}:${pick(value)}:${pick(value.toDouble())}"
