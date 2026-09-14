open class ObservingRoot {
    val observed = read()
    open fun read(): Int = 0
}
open class ObservingMiddle : ObservingRoot()
fun virtualCapture(seed: Int): Int {
    class Child : ObservingMiddle() { override fun read(): Int = seed }
    return Child().observed
}
