package supercases

data class Model(val value: Int)
open class Base(val seed: Int) {
    protected open fun calculate(value: Int): Int = seed + value
    open fun result(value: Int): Model = Model(calculate(value))
    open var amount: Int
        get() = seed
        set(value) { mark("B$value") }
}
open class Middle(seed: Int) : Base(seed) {
    override fun result(value: Int): Model = Model(super.result(value).value + 10)
}
