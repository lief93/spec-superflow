package iterationcases

fun listSum(values: List<Int>): Int {
    var result = 0
    for (value in values) result = result + value
    return result
}

fun iterableSum(values: Iterable<Int>): Int {
    var result = 0
    for (value in values) result = result + value
    return result
}

fun arraySum(values: Array<Int>): Int {
    var result = 0
    for (value in values) result = result + value
    return result
}

fun intArraySum(values: IntArray): Int {
    var result = 0
    for (value in values) result = result + value
    return result
}

fun <T> cursor(values: List<T>): Iterator<T> = values.iterator()
fun more(iterator: Iterator<Int>): Boolean = iterator.hasNext()
fun <T> take(iterator: Iterator<T>): T = iterator.next()
fun arrayCursor(values: Array<Int>): Iterator<Int> = values.iterator()
fun intArrayCursor(values: IntArray): IntIterator = values.iterator()
fun takeInt(iterator: IntIterator): Int = iterator.nextInt()
fun moreInt(iterator: IntIterator): Boolean = iterator.hasNext()

fun arrayFactory(a: Int, b: Int): Array<Int> = arrayOf(a, b)
fun intArrayFactory(a: Int, b: Int): IntArray = intArrayOf(a, b)
fun emptyArrayFactory(): Array<String> = arrayOf<String>()
fun arrayRead(values: Array<Int>, index: Int): Int = values[index]
fun intArrayRead(values: IntArray, index: Int): Int = values[index]
fun arraySize(values: Array<Int>): Int = values.size
fun intArraySize(values: IntArray): Int = values.size
fun arrayWrite(values: Array<Int>, index: Int, value: Int) { values[index] = value }
fun intArrayWrite(values: IntArray, index: Int, value: Int) { values[index] = value }

fun composed(first: Int, last: Int, stride: Int): Int {
    var result = 0
    for (value in first until last step stride) result = result + value
    return result
}

fun untilValue(first: Int, last: Int): IntRange = first until last
fun downValue(first: Int, last: Int): IntProgression = first downTo last
fun rangeValue(first: Int, last: Int): IntRange = first..last
fun stepValue(values: IntProgression, stride: Int): IntProgression = values step stride
fun reversedValue(values: IntProgression): IntProgression = values.reversed()
fun progressionCursor(values: IntProgression): IntIterator = values.iterator()
fun progressionFirst(values: IntProgression): Int = values.first
fun progressionLast(values: IntProgression): Int = values.last
fun progressionStep(values: IntProgression): Int = values.step

fun modifiedCursor(): Iterator<Int> {
    val values = mutableListOf(1, 2)
    val iterator = values.iterator()
    values.add(3)
    return iterator
}

fun replacedArrayCursor(): Iterator<Int> {
    val values = arrayOf(1, 2)
    val iterator = values.iterator()
    values[0] = 9
    return iterator
}

fun replacedIntArrayCursor(): IntIterator {
    val values = intArrayOf(1, 2)
    val iterator = values.iterator()
    values[0] = 9
    return iterator
}
