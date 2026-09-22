package collectionmapcommon

fun mapShift(values: List<Int>): List<Int> = values.map { it + 1 }

fun mapEvenHalves(values: Iterable<Int>): List<Int> =
    values.mapNotNull { value -> if (value % 2 == 0) value / 2 else null }
