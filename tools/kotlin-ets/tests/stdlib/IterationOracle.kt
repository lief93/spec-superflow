package iterationcases

private fun record(expression: String, operation: () -> Any?) {
    val result = try {
        val value = operation()
        "\"value\":" + when (value) {
            null -> "null"
            is Int, is Boolean -> value.toString()
            is List<*> -> value.toString()
            else -> error("Unexpected oracle result: $value")
        }
    } catch (failure: Exception) {
        check(failure is NoSuchElementException || failure is ConcurrentModificationException ||
            failure is ArrayIndexOutOfBoundsException || failure is IllegalArgumentException)
        "\"throws\":\"${failure.javaClass.simpleName}\""
    }
    println("{\"expression\":\"$expression\",$result}")
}

fun main() {
    for (values in listOf(emptyList(), listOf(3), listOf(3, -1, 2))) {
        record("listSum($values)") { listSum(values) }
        record("iterableSum($values)") { iterableSum(values) }
        record("arraySum($values)") { arraySum(values.toTypedArray()) }
        record("intArraySum($values)") { intArraySum(values.toIntArray()) }
    }
    record("take(cursor([null,2]))") { take(cursor(listOf(null, 2))) }
    record("take(cursor([]))") { take(cursor(emptyList<Int>())) }
    record("more(cursor([]))") { more(cursor(emptyList())) }
    record("more(cursor([1]))") { more(cursor(listOf(1))) }
    record("take(arrayCursor([7,8]))") { take(arrayCursor(arrayOf(7, 8))) }
    record("take(arrayCursor([]))") { take(arrayCursor(arrayOf<Int>())) }
    record("takeInt(intArrayCursor([7,8]))") { takeInt(intArrayCursor(intArrayOf(7, 8))) }
    record("takeInt(intArrayCursor([]))") { takeInt(intArrayCursor(intArrayOf())) }
    record("moreInt(intArrayCursor([]))") { moreInt(intArrayCursor(intArrayOf())) }
    record("arrayFactory(3,4)") { arrayFactory(3, 4).toList() }
    record("intArrayFactory(3,4)") { intArrayFactory(3, 4).toList() }
    record("emptyArrayFactory()"){ emptyArrayFactory().toList() }
    record("arraySize([1,2])") { arraySize(arrayOf(1, 2)) }
    record("intArraySize([1,2])") { intArraySize(intArrayOf(1, 2)) }
    for (index in listOf(-1, 0, 1, 2)) {
        record("arrayRead([4,8],$index)") { arrayRead(arrayOf(4, 8), index) }
        record("intArrayRead([4,8],$index)") { intArrayRead(intArrayOf(4, 8), index) }
        record("(() => { const v = [4,8]; arrayWrite(v,$index,9); return v; })()") {
            val values = arrayOf(4, 8); arrayWrite(values, index, 9); values.toList()
        }
        record("(() => { const v = [4,8]; intArrayWrite(v,$index,9); return v; })()") {
            val values = intArrayOf(4, 8); intArrayWrite(values, index, 9); values.toList()
        }
    }
    record("more(modifiedCursor())") { more(modifiedCursor()) }
    record("take(modifiedCursor())") { take(modifiedCursor()) }
    record("take(replacedArrayCursor())") { take(replacedArrayCursor()) }
    record("takeInt(replacedIntArrayCursor())") { takeInt(replacedIntArrayCursor()) }
    record("(() => { const i = cursor([1,2]); return [more(i),take(i),more(i),take(i),more(i)]; })()") {
        val i = cursor(listOf(1, 2)); listOf(more(i), take(i), more(i), take(i), more(i))
    }
    record("takeInt(progressionCursor(rangeValue(-2147483648,2147483647)))") {
        takeInt(progressionCursor(rangeValue(Int.MIN_VALUE, Int.MAX_VALUE)))
    }
    for (args in listOf(listOf(-7, 8, 3), listOf(3, 1, 2), listOf(Int.MIN_VALUE, Int.MIN_VALUE, 2),
        listOf(Int.MIN_VALUE, Int.MAX_VALUE, Int.MAX_VALUE), listOf(3, 1, 0), listOf(3, 1, -1))) {
        val (first, last, stride) = args
        record("composed($first,$last,$stride)") { composed(first, last, stride) }
        record("progressionLast(stepValue(untilValue($first,$last),$stride))") {
            progressionLast(stepValue(untilValue(first, last), stride))
        }
        record("progressionFirst(reversedValue(stepValue(downValue($last,$first),$stride)))") {
            progressionFirst(reversedValue(stepValue(downValue(last, first), stride)))
        }
    }
    record("progressionStep(stepValue(downValue(8,-7),3))") { progressionStep(stepValue(downValue(8, -7), 3)) }
    record("moreInt(progressionCursor(untilValue(-2147483648,-2147483648)))") {
        moreInt(progressionCursor(untilValue(Int.MIN_VALUE, Int.MIN_VALUE)))
    }
    record("takeInt(progressionCursor(untilValue(-2147483648,-2147483648)))") {
        takeInt(progressionCursor(untilValue(Int.MIN_VALUE, Int.MIN_VALUE)))
    }
}
