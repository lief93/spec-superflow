open class Result
class Specific : Result()
open class Base { open fun <T> select(value: T): Result = Result() }
class Derived : Base() { override fun <T> select(value: T): Specific = Specific() }
