interface Base { fun <T> select(value: T): T }
class Derived : Base { override fun <T> select(value: T): Int = 1 }
