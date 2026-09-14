package classboundaries

fun captured(seed: Int): Int {
    class Captured {
        fun read(): Int = seed
    }
    return Captured().read()
}

fun sharedCapture(seed: Int): Int {
    var total = seed
    class Counter {
        fun increment() { total += 1 }
        fun read(): Int = total
    }
    val first = Counter()
    val second = Counter()
    first.increment()
    return second.read()
}

class CaptureHolder(var value: Int)

fun objectCapture(seed: Int): Int {
    val holder = CaptureHolder(seed)
    class Reader {
        fun read(): Int = holder.value
    }
    val reader = Reader()
    holder.value += 2
    return reader.read()
}
