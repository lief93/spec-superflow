package localfixture

fun <T> localIdentity(value: T): T {
    fun <U> keep(input: U): U = input
    return keep(value)
}

fun <T> localGenericCapture(value: T, depth: Int): T {
    fun visit(remaining: Int): T = if (remaining == 0) value else visit(remaining - 1)
    return visit(depth)
}

fun <T> localGenericMutation(value: T, replacement: T): T {
    var current = value
    fun replace() {
        current = replacement
    }
    replace()
    return current
}

fun localRecursion(seed: Int): Int {
    fun sum(value: Int): Int = if (value <= 0) seed else value + sum(value - 1)
    return sum(4)
}

fun sharedCapture(seed: Int): String {
    var value = seed
    fun add(delta: Int): Int {
        value += delta
        return value
    }
    fun read(): Int = value
    val first = add(2)
    value += 3
    val second = read()
    val callback: () -> Int = { value += 4; read() }
    val third = callback()
    return "$first:$second:$third:${add(1)}:$value"
}

fun escapingCapture(seed: Int): () -> Int {
    var value = seed
    fun next(): Int {
        value += 1
        return value
    }
    return { next() }
}

fun localOrder(seed: Int): String {
    var trace = ""
    fun argument(label: String, value: Int): Int {
        trace += label
        return value
    }
    fun combine(left: Int, right: Int = argument("D", left + 1)): Int = left * 10 + right
    val first = combine(right = argument("R", seed + 1), left = argument("L", seed))
    val second = combine(argument("A", seed))
    return "$first:$second:$trace"
}

fun nestedCapture(seed: Int): Int {
    fun outer(delta: Int): Int {
        fun inner(extra: Int): Int = seed + delta + extra
        return inner(3)
    }
    return outer(2)
}

class LocalCounter(var value: Int) {
    fun advance(delta: Int): Int {
        fun add(): Int {
            value += delta
            return value
        }
        return add()
    }
}

fun localsScenario(seed: Int): String {
    val next = escapingCapture(seed)
    val other = escapingCapture(seed + 10)
    return "${localIdentity(seed)}:${localGenericCapture("item", 3)}:${localRecursion(seed)}" +
        "|${sharedCapture(seed)}|${next()}:${next()}:${other()}:${next()}" +
        "|${localOrder(seed)}|${nestedCapture(seed)}|${LocalCounter(seed).advance(3)}" +
        "|${localGenericMutation("old", "new")}:${localGenericMutation(seed, seed + 1)}"
}
