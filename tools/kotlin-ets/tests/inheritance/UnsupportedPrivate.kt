open class PrivateBase {
    private fun value(): Int = 1
    fun read(): Int = value()
}
class PrivateChild : PrivateBase() { fun value(): Int = 2 }
