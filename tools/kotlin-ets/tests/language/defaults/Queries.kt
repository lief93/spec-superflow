package defaultcases

open class Default : Label, PropertyDefault { override fun base(): Int = 3 }
class GrandChild : Default()
class CounterValue(override var total: Int) : Counter
class Child : Parent(), Extended, Left, Right {
    override fun base(): Int = super.base() + 1
    override fun rank(): Int = super<Left>.rank() + super<Right>.rank()
}
class Override : Label {
    override fun base(): Int = 5
    override fun model(extra: Int): Model = Model(extra * 2)
}
val selected = mapOf(Model(5) to Stage.Last)
fun query(label: Label, extra: Int): Model = label.model(extra)
fun lookup(model: Model): Stage? = selected[model]
