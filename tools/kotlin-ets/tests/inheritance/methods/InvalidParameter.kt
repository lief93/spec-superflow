interface Base { fun <T> select(value: T): T }
class Derived : Base { override fun <T> select(value: Int): T = throw Exception() }
