package filtersymbols

import kotlin.collections.filter as retain

fun list(values: List<Int>, predicate: (Int) -> Boolean): List<Int> = values.retain(predicate)
fun iterable(values: Iterable<String>, predicate: (String) -> Boolean): List<String> = values.filterNot(predicate)
fun nullable(values: MutableList<Int?>, predicate: (Int?) -> Boolean): List<Int?> = values.retain(predicate)
