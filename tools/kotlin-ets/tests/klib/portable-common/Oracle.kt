package portableconsumer

fun main() {
    val cases = listOf(1 to 4, 4 to 1, -2 to 2, 0 to 0,
        Int.MAX_VALUE - 1 to Int.MAX_VALUE, Int.MIN_VALUE to Int.MIN_VALUE + 1,
        Int.MIN_VALUE to Int.MIN_VALUE, Int.MAX_VALUE to Int.MAX_VALUE,
        Int.MAX_VALUE to Int.MIN_VALUE)
    for ((first, last) in cases) {
        val range = first..last
        val nativeMapped = range.map { it + 1 }
        val nativeStrings = range.map { "v=$it" }
        val nativeNullable = range.map { if (it % 2 == 0) null else it }
        var nativeOrder = ""
        range.map { nativeOrder += "$it,"; it }
        check(mapped(first, last) == nativeMapped)
        check(strings(first, last) == nativeStrings)
        check(nullable(first, last) == nativeNullable)
        check(order(first, last) == nativeOrder)
        println(listOf(nativeMapped.joinToString(","), nativeStrings.joinToString(","),
            nativeNullable.joinToString(","), nativeOrder).joinToString("|"))
        val nativeCursor = range.iterator()
        while (nativeCursor.hasNext()) nativeCursor.next()
        val nativeFailure = runCatching { nativeCursor.next() }.exceptionOrNull()
        val portableFailure = runCatching { exhaustedAfter(first, last) }.exceptionOrNull()
        check(nativeFailure is NoSuchElementException && nativeFailure.message == null)
        check(portableFailure is NoSuchElementException && portableFailure.message == null)
    }
    val range = 4..5
    val left = range.iterator()
    val right = range.iterator()
    val independentExpected = "${left.next()},${left.next()},${right.next()},${left.hasNext()},${right.hasNext()}"
    check(independent() == independentExpected)
    println(independentExpected)
    var trace = ""
    val failure = IllegalStateException("callback sentinel")
    val thrown = runCatching {
        callback(1, 4) { trace += "$it,"; if (it == 3) throw failure; it }
    }.exceptionOrNull()
    check(thrown === failure && trace == "1,2,3,")
    var nativeTrace = ""
    val nativeThrown = runCatching {
        (1..4).map { nativeTrace += "$it,"; if (it == 3) throw failure; it }
    }.exceptionOrNull()
    check(nativeThrown === failure && nativeTrace == trace)
    println(trace)
}
