package virtualoverloads

interface Selector<T> {
    fun choose(value: T): T
    fun choose(value: Int, extra: Int): Int
}

interface TextSelector { fun choose(value: String): String }

open class Base<T> : Selector<T> {
    override fun choose(value: T): T = value
    override fun choose(value: Int, extra: Int): Int = value + extra
    open fun choose(value: Double): String = "base-double"
    fun unchanged(value: Int): Int = value
    fun choose_0(value: Int): Int = value + 4
    open fun <V> selectItem(value: V): V = value
    open fun selectItem(value: Int, extra: Int): Int = value + extra
}

open class Defaults(val seed: Int) {
    open fun label(value: Int = seed): String = "base:$value"
    open fun label(value: String): String = "text:$value"
}

class Unrelated { fun choose(value: Int): Int = value + 7 }

open class Numeric {
    open fun choose(value: Int): Int = value + 1
    open fun choose(value: Double): Int = 17
}
