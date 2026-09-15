package exceptioncases

fun sourceFailure(): Int = throw PageFailure(7, "page")

var attempts = 0
fun initializeFailure(): Int { attempts++; throw IllegalStateException("initialize") }

var trace = ""
fun mark(value: String) { trace += value }
fun value(mode: Int): Int = try {
    mark("t")
    if (mode == 1) throw IllegalArgumentException("bad")
    if (mode == 2) throw IllegalStateException("state")
    8
} catch (failure: IllegalArgumentException) {
    mark("a")
    3
} catch (failure: RuntimeException) {
    mark("r")
    4
} finally { mark("f") }

fun early(mode: Int): Int {
    val result = try {
        if (mode == 1) return 11
        7
    } finally {
        mark("e")
        if (mode == 2) return 22
    }
    return result + 1
}
fun loop(): Int {
    var index = 0
    var result = 0
    while (index < 5) {
        index++
        try {
            if (index == 2) continue
            if (index == 4) break
            result += index
        } finally { mark("$index") }
    }
    return result
}
fun rethrow(): Int {
    try {
        try { throw IllegalArgumentException("nested") }
        catch (failure: RuntimeException) { mark("i"); throw failure }
        finally { mark("j") }
    } catch (failure: IllegalArgumentException) { mark("o"); return 6 }
}
fun overrideThrow(): Int { try { return 1 } finally { throw IllegalStateException("override") } }
fun divide(value: Int): Int = 7 / value
fun nullValue(): String? = null
fun anyValue(): Any = "text"
