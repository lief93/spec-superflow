open class CustomGetterBase {
    private val computed: Int get() = read()
    val observed = computed
    open fun read(): Int = 0
}
fun customGetterCapture(seed: Int): Int {
    class Child : CustomGetterBase() { override fun read(): Int = seed }
    return Child().observed
}
