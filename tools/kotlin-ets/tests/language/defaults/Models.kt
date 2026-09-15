package defaultcases

data class Model(val value: Int)
enum class Stage { First, Last }
interface Label {
    fun base(): Int
    fun model(extra: Int): Model = Model(base() + extra)
    fun stage(): Stage = Stage.Last
}
interface Extended : Label {
    override fun model(extra: Int): Model = Model(super<Label>.model(extra).value + 10)
}
interface Left { fun rank(): Int = 1 }
interface Right { fun rank(): Int = 2 }
interface PropertyDefault { val value: Int get() = 7 }
interface Counter {
    var total: Int
    fun add(value: Int) { total += value }
}
open class Parent { open fun base(): Int = 2 }
