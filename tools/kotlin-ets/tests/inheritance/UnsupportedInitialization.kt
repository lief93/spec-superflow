open class InitializationBase {
    val initial: Int = read()
    open fun read(): Int = 1
}
class InitializationChild : InitializationBase() {
    private val value = 3
    override fun read(): Int = value
}
