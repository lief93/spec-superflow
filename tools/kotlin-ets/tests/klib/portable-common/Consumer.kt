package portableconsumer

import portablecommon.IntSpan
import portablecommon.mapBody

fun mapped(first: Int, last: Int): List<Int> = IntSpan(first, last).mapBody { it + 1 }

fun strings(first: Int, last: Int): List<String> = IntSpan(first, last).mapBody { "v=$it" }

fun nullable(first: Int, last: Int): List<Int?> = IntSpan(first, last).mapBody {
    if (it % 2 == 0) null else it
}

fun order(first: Int, last: Int): String {
    var trace = ""
    IntSpan(first, last).mapBody { trace += "$it,"; it }
    return trace
}

fun callback(first: Int, last: Int, transform: (Int) -> Int): List<Int> =
    IntSpan(first, last).mapBody(transform)

fun exhaustedAfter(first: Int, last: Int): Int {
    val cursor = IntSpan(first, last).iterator()
    while (cursor.hasNext()) cursor.next()
    return cursor.next()
}

fun independent(): String {
    val range = IntSpan(4, 5)
    val left = range.iterator()
    val right = range.iterator()
    return "${left.next()},${left.next()},${right.next()},${left.hasNext()},${right.hasNext()}"
}
