open class Base { open fun <T> select(value: T): T = value }
class Derived : Base() { override fun <T> select(value: T): T = super.select(value) }
