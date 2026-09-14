package filterrejected
fun ints(values: IntArray): List<Int> = values.filterNot { it > 0 }
