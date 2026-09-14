open class SecondaryObserver {
    val observed: Int
    constructor() { observed = read() }
    open fun read(): Int = 0
}
fun secondaryCapture(seed: Int): Int {
    class Child : SecondaryObserver() { override fun read(): Int = seed }
    return Child().observed
}
