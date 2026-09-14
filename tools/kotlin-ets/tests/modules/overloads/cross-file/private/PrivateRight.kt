package privateoverloads

private fun localOffset(value: Int): Int = value + 10
fun privateOrPublic(value: Double): Int = if (value > 0.0) 20 else 30
fun pick(value: Double): Int = if (value > 0.0) 200 else 300
fun mixed(value: Boolean): Int = if (value) 60 else 70

fun rightPrivateCase(value: Int): String =
    "${localOffset(value)}:${privateOrPublic(value.toDouble())}:${mixed(value > 0)}"
