package genericfixture

class Box<T>(var value: T) {
    fun read(): T = value
    fun chooseValue(other: T = value): T = other
    fun <R> mapped(action: (T) -> R): Box<R> = Box(action(value))
    var observed: T
        get() = value
        set(next) { value = next }
}

class PairBox<A, B>(val left: A, val right: B) {
    fun swapped(): PairBox<B, A> = PairBox(right, left)
}

fun classCases(seed: Int): String {
    val box = Box(seed)
    val initial = box.observed
    box.observed = seed + 1
    val mapped = box.mapped { it + 4 }
    val nested = Box(Box("nested"))
    val pair = PairBox(seed, "right").swapped()
    val optional = Box<String?>(null)
    val absent = optional.read()
    optional.observed = "present"
    return "$initial:${box.read()}:${box.chooseValue()}:${box.chooseValue(seed + 2)}:${mapped.unbox()}:${nested.value.value}:${pair.left}:${pair.right}:$absent:${optional.read()}"
}
