package filtercases

private fun record(expression: String, actual: Any, expected: Any) {
    check(actual == expected) { "$expression: $actual != $expected" }
    val value = if (actual is String) "\"$actual\"" else actual.toString()
    println("{\"expression\":\"$expression\",\"value\":$value}")
}

fun main() {
    val values = listOf(-2, 0, 3, 3, 1)
    record("positive([-2,0,3,3,1])", positive(values), listOf(3, 3, 1))
    record("nonPositive([-2,0,3,3,1])", nonPositive(values), listOf(-2, 0))
    record("emptyFilter()", emptyFilter(), emptyList<Int>())
    record("emptyFilterNot()", emptyFilterNot(), emptyList<Int>())
    record("mutableSelected([-2,0,3,3,1])", mutableSelected(values.toMutableList()), listOf(3, 3, 1))
    record("mutableRejected([-2,0,3,3,1])", mutableRejected(values.toMutableList()), listOf(-2, 0))
    record("selected([null,2,null], v => v !== null)",
        selected(listOf(null, 2, null)) { it != null }, listOf(2))
    record("rejected([null,2,null], v => v !== null)",
        rejected(listOf(null, 2, null)) { it != null }, listOf(null, null))
    record("selected(['ab','c','def'], v => v.length > 1).length",
        selected(listOf("ab", "c", "def")) { it.length > 1 }.size, 2)
    record("rejected(['ab','c','def'], v => v.length > 1).length",
        rejected(listOf("ab", "c", "def")) { it.length > 1 }.size, 1)
    for (keep in listOf(false, true)) {
        val nullable = listOf(null, 2, null)
        record("nullableSelected([null,2,null],$keep)", nullableSelected(nullable, keep),
            if (keep) nullable else emptyList<Int?>())
        record("nullableRejected([null,2,null],$keep)", nullableRejected(nullable, keep),
            if (keep) emptyList<Int?>() else nullable)
        record("selected([-2,0,3,3,1], () => $keep)", selected(values) { keep },
            if (keep) values else emptyList<Int>())
        record("rejected([-2,0,3,3,1], () => $keep)", rejected(values) { keep },
            if (keep) emptyList<Int>() else values)
        for (invert in listOf(false, true)) {
            record("traceFilter([3,1,2],$invert,$keep)", traceFilter(listOf(3, 1, 2), invert, keep),
                if (keep != invert) "3/312/3/3" else "3/312/0/3")
            record("traceFilter([],$invert,$keep)", traceFilter(emptyList(), invert, keep), "0/0/0/0")
        }
    }
    for (invert in listOf(false, true)) {
        record("sourceAfterFilter($invert)", sourceAfterFilter(invert),
            if (invert) listOf(4, 3, 1, 2, 9, 1, 1) else listOf(4, 3, 1, 2, 9, 2, 3))
        record("evaluationOrder($invert)", evaluationOrder(invert), listOf(1, 2, 13, 11, 12))
        val seen = mutableListOf<Int>()
        try {
            explodingFilter(listOf(1, 2, 3), seen, invert)
            error("Predicate must throw")
        } catch (_: ArithmeticException) {
            record("(() => { const seen = []; try { explodingFilter([1,2,3],seen,$invert); } " +
                "catch (e) { if (!e.message.includes('ArithmeticException')) throw e; return seen; } })()",
                seen, listOf(1, 2))
        }
        val modified = mutableListOf(1, 2)
        try {
            modifyingFilter(modified, invert)
            error("Structural mutation must throw")
        } catch (_: ConcurrentModificationException) {
            record("(() => { const v = [1,2]; try { modifyingFilter(v,$invert); } " +
                "catch (e) { if (!e.message.includes('ConcurrentModificationException')) throw e; return v; } })()",
                modified, listOf(1, 2, 1))
        }
    }
}
