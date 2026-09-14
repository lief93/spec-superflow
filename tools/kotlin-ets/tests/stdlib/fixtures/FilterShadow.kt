package filtershadow

fun List<Int>.filter(predicate: (Int) -> Boolean): List<Int> = listOf(77)
fun Iterable<Int>.filterNot(predicate: (Int) -> Boolean): List<Int> = listOf(88)
fun shadowFilter(): Int = listOf(1, 2).filter { true }[0]
fun shadowFilterNot(): Int = listOf(1, 2).filterNot { false }[0]
