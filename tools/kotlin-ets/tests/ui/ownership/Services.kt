package ownership

class Counter {
    var value: Int = 0
    fun add(delta: Int) { value += delta }
}

fun makeAction(counter: Counter, delta: Int): () -> Unit = { counter.add(delta) }

fun replay(seed: Int): String {
    val counter = Counter()
    val first = makeAction(counter, seed)
    val second = makeAction(counter, 2)
    first()
    second()
    first()
    return "${counter.value}"
}
