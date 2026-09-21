package klibclosure

fun filterEven(values: List<Int>): List<Int> = values.filter { it % 2 == 0 }

fun mapPlusOne(values: List<Int>): List<Int> = values.map { it + 1 }

fun firstOrNullValue(values: List<Int>): Int? = values.firstOrNull()

fun scenario(kind: String, values: List<Int>): String = when (kind) {
    "filter" -> filterEven(values).joinToString(",")
    "map" -> mapPlusOne(values).joinToString(",")
    "first" -> firstOrNullValue(values)?.toString() ?: "null"
    else -> error(kind)
}
