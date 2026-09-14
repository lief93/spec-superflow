open class Base { fun select(value: Int): Int = value }
class Child : Base() { fun select(value: String): String = value }
