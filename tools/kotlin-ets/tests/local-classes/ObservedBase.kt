package classboundaries

open class ObservedBase {
    val observed = read()
    open fun read(): Int = 0
}
fun observedBase(seed: Int): Int {
    class Child : ObservedBase() { override fun read(): Int = seed }
    return Child().observed
}
