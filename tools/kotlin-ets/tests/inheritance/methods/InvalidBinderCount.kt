interface Base { fun <T> select(value: T): T }
class Derived : Base { override fun <T, U> select(value: T): T = value }
