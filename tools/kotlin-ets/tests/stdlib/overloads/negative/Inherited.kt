package overloadnegative

open class Parent {
    open fun choose(value: Int): Int = value
    open fun choose(value: Double): Int = 20
}
class Child : Parent()
fun inherited(values: List<Int>): List<Int> = values.map { Child().choose(it) }
