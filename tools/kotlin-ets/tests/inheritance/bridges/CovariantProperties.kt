interface CovariantView<T> { val value: T }
interface RefinedView : CovariantView<CovariantValue> { override val value: SpecificValue }
class StoredRefinedView(override val value: SpecificValue) : RefinedView

open class ReadonlyBase<T>(initial: T) { open val value: T = initial }
class ReadonlyChild(seed: Int) : ReadonlyBase<CovariantValue>(CovariantValue(seed)) {
    override val value: SpecificValue = SpecificValue(seed + 1)
}
abstract class AbstractReadonly : CovariantView<CovariantValue> {
    abstract override val value: CovariantValue
}
class ConcreteReadonly(seed: Int) : AbstractReadonly() {
    override val value: SpecificValue = SpecificValue(seed)
}

class ReadTrace { var trace: String = "" }
class ComputedReadonly(private val seed: Int, private val effects: ReadTrace) : CovariantView<CovariantValue> {
    override val value: SpecificValue
        get() { effects.trace += "G"; return SpecificValue(seed) }
}
class MutableRefinement(seed: Int) : CovariantView<CovariantValue> {
    override var value: SpecificValue = SpecificValue(seed)
}
fun <T : CovariantView<CovariantValue>> boundedRead(view: T): Int = view.value.value

fun covariantProperties(seed: Int): String {
    val stored: CovariantView<CovariantValue> = StoredRefinedView(SpecificValue(seed))
    val child = ReadonlyChild(seed)
    val base: ReadonlyBase<CovariantValue> = child
    val concrete: AbstractReadonly = ConcreteReadonly(seed)
    val trace = ReadTrace()
    val computed = ComputedReadonly(seed, trace)
    val broad: CovariantView<CovariantValue> = computed
    val mutable = MutableRefinement(seed)
    val readOnly: CovariantView<CovariantValue> = mutable
    mutable.value = SpecificValue(seed + 2)
    return "${stored.value.value}:${base.value.value}:${child.value.value}:${concrete.value.value}:${boundedRead(computed)}:${broad.value.value}:${readOnly.value.value}:${trace.trace}"
}
