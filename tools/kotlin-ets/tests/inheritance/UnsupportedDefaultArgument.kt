open class DefaultBase { open fun apply(value: Int = 3): Int = value }
class DefaultChild : DefaultBase() { override fun apply(value: Int): Int = value + 1 }
fun callDefault(value: DefaultBase): Int = value.apply()
