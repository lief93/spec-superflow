package collectionmapindexedcommon

fun mapIndexedSum(values: List<Int>): List<Int> =
    values.mapIndexed { index, value -> index + value }

fun mapIndexedEvenOffsets(values: Iterable<Int>): List<Int> =
    values.mapIndexedNotNull { index, value -> if (value % 2 == 0) index - value else null }
