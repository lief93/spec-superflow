package collectioncommon

fun filterEven(values: List<Int>): List<Int> = values.filter { it % 2 == 0 }

fun filterOdd(values: Iterable<Int>): List<Int> = values.filterNot { it % 2 == 0 }
