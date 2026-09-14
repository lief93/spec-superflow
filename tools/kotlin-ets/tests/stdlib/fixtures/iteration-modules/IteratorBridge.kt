package iterationmodules

fun transfer(first: Int, second: Int): Int = consumePair(produce(listOf(first, second)))
fun continuedCursor(): Int {
    val iterator = produce(listOf(1, 2, 3))
    consumeNext(iterator)
    return consumePair(iterator)
}
fun nullableTransfer(value: Int?): Int? = consumeNext(produce(listOf(value)))
fun rangeTransfer(first: Int, last: Int): Int = consumeNext(produceRange(first, last))
