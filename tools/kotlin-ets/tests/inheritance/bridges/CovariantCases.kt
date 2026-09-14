open class CovariantValue(val value: Int)
class SpecificValue(value: Int) : CovariantValue(value)

interface Producer<T> { fun produce(seed: Int): T }
open class ValueProducer : Producer<CovariantValue> {
    override fun produce(seed: Int): CovariantValue = CovariantValue(seed)
}
class SpecificProducer : ValueProducer() {
    override fun produce(seed: Int): SpecificValue = SpecificValue(seed + 1)
}
class InheritedProducer : ValueProducer()

interface NullableProducer { fun produce(seed: Int): CovariantValue? }
class PresentProducer : NullableProducer {
    override fun produce(seed: Int): SpecificValue = SpecificValue(seed)
}

interface BoundedProducer { fun <T : CovariantValue> retain(value: T): CovariantValue }
class IdentityProducer : BoundedProducer {
    override fun <R : CovariantValue> retain(value: R): R = value
}

interface JoinedProducer<T> {
    fun produce(value: T): CovariantValue
    fun produce(value: String): CovariantValue
}
class JoinedSpecificProducer : JoinedProducer<String> {
    override fun produce(value: String): SpecificValue = SpecificValue(value.length)
}
open class ExistingProducer {
    open fun produce(value: String): SpecificValue = SpecificValue(value.length + 1)
}
class InheritedJoinedProducer : ExistingProducer(), JoinedProducer<String>
class OverrideJoinedProducer : ExistingProducer(), JoinedProducer<String> {
    override fun produce(value: String): SpecificValue = SpecificValue(value.length + 2)
}

fun <T> produced(factory: JoinedProducer<T>, value: T): CovariantValue = factory.produce(value)
fun <T> fixedProduced(factory: JoinedProducer<T>, value: String): CovariantValue = factory.produce(value)

fun covariantDispatch(seed: Int): String {
    val base: ValueProducer = SpecificProducer()
    val contract: Producer<CovariantValue> = base
    val inherited: Producer<CovariantValue> = InheritedProducer()
    val direct: SpecificValue = SpecificProducer().produce(seed)
    val original: Factory = Dogs()
    return "${base.produce(seed).value}:${contract.produce(seed).value}:${inherited.produce(seed).value}:${direct.value}:${original.make(seed) is Dog}:${original.make("s") is Dog}"
}

fun covariantBounds(seed: Int): Int {
    val direct = IdentityProducer().retain(SpecificValue(seed))
    val throughInterface: BoundedProducer = IdentityProducer()
    val broad: CovariantValue = throughInterface.retain(direct)
    return broad.value
}

fun covariantNullable(seed: Int): Int {
    val contract: NullableProducer = PresentProducer()
    return contract.produce(seed)?.value ?: -1
}

fun covariantJoined(seed: Int): String {
    val value = "v$seed"
    val direct = JoinedSpecificProducer()
    val inherited = InheritedJoinedProducer()
    val overridden = OverrideJoinedProducer()
    return "${produced(direct, value).value}:${fixedProduced(direct, value).value}:${produced(inherited, value).value}:${fixedProduced(inherited, value).value}:${produced(overridden, value).value}:${fixedProduced(overridden, value).value}"
}
