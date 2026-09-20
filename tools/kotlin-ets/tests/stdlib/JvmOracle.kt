package stdlibcases

private fun quote(value: String): String = "\"" + value.replace("\\", "\\\\")
    .replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + "\""

private fun record(expression: String, operation: () -> Any) {
    val outcome = try {
        val actual = operation()
        val value = when (actual) {
            is String -> quote(actual)
            is Int, is Boolean -> actual.toString()
            else -> error("Unexpected oracle value")
        }
        "\"value\":$value"
    } catch (error: ArithmeticException) {
        "\"throws\":\"ArithmeticException\""
    } catch (error: IndexOutOfBoundsException) {
        "\"throws\":\"IndexOutOfBoundsException\""
    } catch (error: ConcurrentModificationException) {
        "\"throws\":\"ConcurrentModificationException\""
    }
    println("{\"expression\":${quote(expression)},$outcome}")
}

fun main() {
    record("arithmetic(7, 3)") { arithmetic(7, 3) }
    record("arithmetic(-7, 3)") { arithmetic(-7, 3) }
    record("arithmetic(2147483647, 2)") { arithmetic(Int.MAX_VALUE, 2) }
    record("sum(2147483647, 1)") { sum(Int.MAX_VALUE, 1) }
    record("sum(-2147483648, -1)") { sum(Int.MIN_VALUE, -1) }
    record("product(2147483647, 2147483647)") { product(Int.MAX_VALUE, Int.MAX_VALUE) }
    record("quotient(-7, 3)") { quotient(-7, 3) }
    record("quotient(7, -3)") { quotient(7, -3) }
    record("quotient(-2147483648, -1)") { quotient(Int.MIN_VALUE, -1) }
    record("remainder(-7, 3)") { remainder(-7, 3) }
    record("remainder(-2147483648, -1)") { remainder(Int.MIN_VALUE, -1) }
    record("unary(-2147483648)") { unary(Int.MIN_VALUE) }
    for ((a, b) in listOf(-1 to 1, 1 to 1, 1 to -1)) {
        record("less($a, $b)") { less(a, b) }
        record("lessEqual($a, $b)") { lessEqual(a, b) }
        record("greater($a, $b)") { greater(a, b) }
        record("greaterEqual($a, $b)") { greaterEqual(a, b) }
        record("compareValues($a, $b)") { compareValues(a, b) }
    }
    record("compareValues(-2147483648, 2147483647)") { compareValues(Int.MIN_VALUE, Int.MAX_VALUE) }
    for (a in listOf(false, true)) for (b in listOf(false, true)) {
        record("booleanOps($a, $b)") { booleanOps(a, b) }
        record("boolEquality($a, $b)") { boolEquality(a, b) }
    }
    record("(() => { const v = []; eagerAnd(v, false); return v.length; })()") {
        val values = mutableListOf<Int>()
        eagerAnd(values, false)
        values.size
    }
    record("(() => { const v = []; eagerOr(v, true); return v.length; })()") {
        val values = mutableListOf<Int>()
        eagerOr(values, true)
        values.size
    }
    record("stringOps(\"value=\", -7)") { stringOps("value=", -7) }
    record("interpolation(\"result\", 5)") { interpolation("result", 5) }
    record("length(\"A\\uD83D\\uDE00B\")") { length("A\uD83D\uDE00B") }
    record("substring(\"abcde\", 1, 4)") { substring("abcde", 1, 4) }
    record("suffix(\"abcde\", 5)") { suffix("abcde", 5) }
    record("contains(\"AbCd\", \"bC\")") { contains("AbCd", "bC") }
    record("contains(\"AbCd\", \"bc\")") { contains("AbCd", "bc") }
    record("startsWith(\"AbCd\", \"Ab\")") { startsWith("AbCd", "Ab") }
    record("endsWith(\"AbCd\", \"cd\")") { endsWith("AbCd", "cd") }
    record("stringEquality(\"ab\", \"a\" + \"b\")") { stringEquality("ab", "a" + "b") }
    record("emptySize()") { emptySize() }
    record("singleton(9)") { singleton(9) }
    record("listRead(4, 8, 1)") { listRead(4, 8, 1) }
    record("listSize(\"a\", \"b\")") { listSize("a", "b") }
    record("append(5)") { append(5) }
    record("emptyMutableAdd(5)") { emptyMutableAdd(5) }
    record("mapped(10)") { mapped(10) }
    record("mutation(17)") { mutation(17) }
    record("arithmetic(7, 0)") { arithmetic(7, 0) }
    record("remainder(1, 0)") { remainder(1, 0) }
    record("substring(\"abc\", -1, 2)") { substring("abc", -1, 2) }
    record("substring(\"abc\", 2, 1)") { substring("abc", 2, 1) }
    record("substring(\"abc\", 0, 4)") { substring("abc", 0, 4) }
    record("suffix(\"abc\", 4)") { suffix("abc", 4) }
    record("listRead(4, 8, -1)") { listRead(4, 8, -1) }
    record("listRead(4, 8, 2)") { listRead(4, 8, 2) }
    record("indexed([], 0)") { indexed(emptyList(), 0) }
    record("invalidMap()") { invalidMap() }
    record("mappedIterable(10)") { mappedIterable(10) }
    record("mappedSet(10)") { mappedSet(10) }
    record("mappedMutableSet(10)") { mappedMutableSet(10) }
    record("invalidSetMap()") { invalidSetMap() }
}
