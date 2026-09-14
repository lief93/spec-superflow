fun observe(value: EscapingBase): Int = value.read()
open class EscapingBase {
    val observed = observe(this)
    open fun read(): Int = 0
}
fun escapedCapture(seed: Int): Int {
    class Child : EscapingBase() { override fun read(): Int = seed }
    return Child().observed
}
