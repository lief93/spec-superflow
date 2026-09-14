package inheritancefixture

interface Operation {
    fun apply(left: Int, right: Int): Int
}

interface NamedOperation : Operation {
    fun label(): String
}

open class Base(private val seed: Int) : Operation {
    override fun apply(left: Int, right: Int): Int = seed + left - right
    fun inherited(delta: Int): Int = apply(delta, 2)
}

class Derived(seed: Int, private val factor: Int) : Base(seed), NamedOperation {
    override fun apply(left: Int, right: Int): Int = left * factor + right
    override fun label(): String = "derived"
}

class Unchanged(seed: Int) : Base(seed)

abstract class AbstractOperation : Operation {
    abstract override fun apply(left: Int, right: Int): Int
    fun twice(value: Int): Int = apply(value, value)
}

class Concrete : AbstractOperation() {
    override fun apply(left: Int, right: Int): Int = left - right
}

class Effects {
    var trace: String = ""
    fun number(label: String, value: Int): Int { trace += label; return value }
    fun receiver(value: Base): Base { trace += "R"; return value }
    fun mark(label: String) { trace += label }
}

open class Initialized(effects: Effects, initial: Int) {
    val stored: Int = effects.number("B", initial)
    init { effects.mark("I") }
    open fun read(): Int = stored
}

class InitializedChild(effects: Effects, initial: Int) : Initialized(effects, effects.number("A", initial)) {
    private val own: Int = effects.number("C", initial + 1)
    init { effects.mark("D") }
    override fun read(): Int = own
}

fun invokeOperation(operation: Operation, left: Int, right: Int): Int = operation.apply(left, right)
fun invokeBase(base: Base, delta: Int): Int = base.inherited(delta)
fun invokeNamed(operation: NamedOperation, left: Int): String = "${operation.label()}:${operation.apply(left, 3)}"
fun select(value: Boolean, seed: Int): Operation = if (value) Derived(seed, 3) else Unchanged(seed)

fun dispatch(seed: Int): String {
    val derived = Derived(seed, 3)
    val unchanged = Unchanged(seed)
    return "${invokeOperation(derived, seed, 2)}:${invokeBase(derived, seed)}:${unchanged.apply(seed, 2)}:${derived.inherited(seed)}:${invokeNamed(derived, seed)}"
}

fun abstractDispatch(value: Int): Int {
    val operation: AbstractOperation = Concrete()
    return operation.twice(value)
}

fun callEffects(seed: Int): String {
    val effects = Effects()
    val result = effects.receiver(Derived(seed, 3)).apply(effects.number("L", seed), effects.number("Q", 4))
    return "${effects.trace}:$result"
}

fun constructorEffects(seed: Int): String {
    val effects = Effects()
    val value: Initialized = InitializedChild(effects, effects.number("X", seed))
    return "${effects.trace}:${value.read()}"
}

fun selected(value: Boolean, seed: Int): Int = select(value, seed).apply(seed, 5)

open class PropertyRoot<T>(var value: T) {
    var trace: String = ""
    var computed: T
        get() { trace += "G"; return value }
        set(next) { trace += "S"; value = next }
}

open class PropertyMiddle<T>(value: T) : PropertyRoot<T>(value)
class PropertyLeaf(value: Int) : PropertyMiddle<Int>(value)

class PropertyEffects {
    var trace: String = ""
    fun receiver(value: PropertyLeaf): PropertyLeaf { trace += "R"; return value }
    fun argument(value: Int): Int { trace += "A"; return value }
}

fun propertyDispatch(seed: Int): String {
    val leaf = PropertyLeaf(seed)
    val base: PropertyRoot<Int> = leaf
    val effects = PropertyEffects()
    effects.receiver(leaf).computed = effects.argument(seed + 1)
    val read = leaf.computed
    leaf.value = read + 1
    return "${effects.trace}:${leaf.trace}:${base.value}:${base.computed}"
}

interface PropertyView<T> { val value: T }
interface MutablePropertyView<T> : PropertyView<T> { var current: T }
class StoredView(override val value: Int, override var current: Int) : MutablePropertyView<Int>
class ComputedView(initial: Int) : MutablePropertyView<Int> {
    private var stored: Int = initial
    override val value: Int get() = stored + 1
    override var current: Int
        get() = stored
        set(next) { stored = next + 2 }
}
fun propertyInterface(seed: Int): String {
    val stored: MutablePropertyView<Int> = StoredView(seed, seed)
    val computed: MutablePropertyView<Int> = ComputedView(seed)
    stored.current = seed + 3
    computed.current = seed + 3
    val read: PropertyView<Int> = computed
    return "${stored.value}:${stored.current}:${read.value}:${computed.current}"
}

open class VirtualRoot<T>(initial: T) {
    open var value: T = initial
    fun read(): T = value
    fun write(next: T) { value = next }
}
open class VirtualMiddle<T>(initial: T) : VirtualRoot<T>(initial) {
    override var value: T = initial
}
class VirtualLeaf(initial: Int, private val effects: Effects) : VirtualMiddle<Int>(initial) {
    override var value: Int = initial
        get() { effects.mark("G"); return field }
        set(next) { effects.mark("S"); field = next + 1 }
}
class VirtualUnchanged(initial: Int) : VirtualMiddle<Int>(initial)
class VirtualEffects {
    var trace: String = ""
    fun receiver(value: VirtualRoot<Int>): VirtualRoot<Int> { trace += "R"; return value }
    fun argument(value: Int): Int { trace += "A"; return value }
}
fun virtualProperties(seed: Int): String {
    val effects = Effects()
    val value: VirtualRoot<Int> = VirtualLeaf(seed, effects)
    val calls = VirtualEffects()
    calls.receiver(value).value += calls.argument(2)
    val first = value.read()
    value.write(seed + 3)
    val second = value.value
    val inherited: VirtualRoot<Int> = VirtualUnchanged(seed)
    inherited.write(seed + 5)
    return "$first:$second:${inherited.read()}:${effects.trace}:${calls.trace}"
}

interface PropertiesContract<T> {
    val title: T
    var current: T
}
abstract class AbstractProperties<T> : PropertiesContract<T> {
    abstract override val title: T
    abstract override var current: T
    fun replace(next: T): T { current = next; return current }
}
abstract class AbstractPropertiesMiddle<T> : AbstractProperties<T>() {
    abstract override val title: T
    abstract override var current: T
}
class ConcreteProperties(override val title: Int, override var current: Int) : AbstractPropertiesMiddle<Int>()
class ComputedProperties(initial: Int) : AbstractProperties<Int>() {
    private var stored: Int = initial
    override val title: Int get() = stored + 1
    override var current: Int
        get() = stored
        set(next) { stored = next + 2 }
}
fun abstractProperties(seed: Int): String {
    val stored: AbstractProperties<Int> = ConcreteProperties(seed, seed)
    val computed: AbstractProperties<Int> = ComputedProperties(seed)
    return "${stored.replace(seed + 1)}:${stored.title}:${computed.replace(seed + 3)}:${computed.title}"
}
