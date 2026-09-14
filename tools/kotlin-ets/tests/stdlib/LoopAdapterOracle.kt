package loopadaptercases

import java.lang.reflect.InvocationTargetException

private fun record(function: String, args: List<Int>, operation: () -> Int) {
    val result = try { "\"value\":${operation()}" } catch (failure: Exception) {
        val cause = if (failure is InvocationTargetException) failure.targetException else failure
        check(cause is IllegalArgumentException)
        "\"throws\":\"IllegalArgumentException: ${cause.message}\""
    }
    println("{\"function\":\"$function\",\"args\":$args,$result}")
}

fun main() {
    check(KotlinVersion.CURRENT.toString() == "2.1.20")
    val official = Class.forName("kotlin.internal.ProgressionUtilKt").getMethod("getProgressionLastElement",
        Int::class.javaPrimitiveType, Int::class.javaPrimitiveType, Int::class.javaPrimitiveType)
    val edges = listOf(Int.MIN_VALUE, Int.MIN_VALUE + 1, -2147483647, -7, -1, 0, 1, 7, Int.MAX_VALUE - 1, Int.MAX_VALUE)
    for (start in edges) for (end in edges) for (step in edges) {
        record("__etsProgressionLastElement", listOf(start, end, step)) { official.invoke(null, start, end, step) as Int }
    }
    val random = java.util.Random(421)
    repeat(300) {
        val args = listOf(random.nextInt(), random.nextInt(), random.nextInt())
        record("__etsProgressionLastElement", args) { official.invoke(null, args[0], args[1], args[2]) as Int }
    }
    val cases = listOf(listOf(-7, 8, 3), listOf(8, -7, 3), listOf(2, 1, 2), listOf(1, 2, 2),
        listOf(Int.MIN_VALUE, Int.MAX_VALUE, Int.MAX_VALUE), listOf(Int.MAX_VALUE, Int.MIN_VALUE, Int.MAX_VALUE),
        listOf(Int.MIN_VALUE, Int.MIN_VALUE, 2), listOf(Int.MAX_VALUE, Int.MAX_VALUE, 2),
        listOf(3, 1, 0), listOf(3, 1, -1), listOf(3, 1, Int.MIN_VALUE))
    for (args in cases) {
        record("ascendingLast", args) { ascendingLast(args[0], args[1], args[2]) }
        record("descendingLast", args) { descendingLast(args[0], args[1], args[2]) }
    }
}
