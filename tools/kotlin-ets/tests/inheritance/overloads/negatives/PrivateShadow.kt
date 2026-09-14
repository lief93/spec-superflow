open class PrivateBase {
    private fun value(input: Int): Int = input
    fun read(input: Int): Int = value(input)
}
class PrivateChild : PrivateBase() { fun value(input: Int): Int = input + 1 }
