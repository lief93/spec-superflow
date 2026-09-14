package filterrejected
fun broadPredicate(values: List<Int>, predicate: (Any) -> Boolean): List<Int> = values.filter(predicate)
