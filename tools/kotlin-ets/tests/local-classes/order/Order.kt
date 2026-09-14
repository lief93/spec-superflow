package classorder

class Outer {
    open class Base(val value: Int) {
        fun read(): Int = value + 1
    }
}

class Derived(value: Int) : Outer.Base(value)
class Earlier(value: Int) : Later.Base(value)

class Later {
    open class Base(val value: Int) {
        fun read(): Int = value - 1
    }
}

fun local(seed: Int): Int {
    open class Parent(val value: Int) {
        fun read(): Int = value
    }
    class Child(value: Int) : Parent(value)
    return Child(seed).read()
}

fun result(value: Int): String = "${Derived(value).read()}/${Earlier(value).read()}/${local(value)}"
