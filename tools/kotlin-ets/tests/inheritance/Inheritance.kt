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
