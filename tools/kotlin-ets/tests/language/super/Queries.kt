package supercases

class Child(seed: Int) : Middle(seed) {
    fun baseSeed(): Int = super.seed
    override fun calculate(value: Int): Int = super.calculate(value) + 100
    override fun result(value: Int): Model = super.result(argument(value))
    override var amount: Int
        get() = super.amount + 1
        set(value) { super.amount = argument(value); mark("C") }
}
fun query(value: Base): Model = value.result(2)
