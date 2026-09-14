package iterationmodules

fun <T> produce(values: List<T>): Iterator<T> = values.iterator()
fun produceRange(first: Int, last: Int): IntIterator = (first..last).iterator()
