open class Parent(val value: Int) { constructor(value: String) : this(value.length) }
class Child(value: String) : Parent(value)
