package overloadfixture

fun beforeDeclaration(seed: Int): String = arity(seed)
fun arity(): String = "zero"
fun arity(value: Int): String = "one:$value"

fun pick(value: Int): String = "int:$value"
fun pick(value: Double): String = "double"
fun pick(value: String): String = "string:$value"
fun pick_0(): String = "preserved"

class FinalMethods(var calls: Int, val choose_0: Int) {
    fun choose(value: Int): String {
        calls = calls + 1
        return "member-int:$value"
    }
    fun choose(value: Double): String {
        calls = calls + 1
        return "member-double"
    }
}

fun <T> selected(value: T): String = "generic"
fun selected(value: Int): String = "concrete:$value"
fun <T> forward(value: T): String = selected(value)

class GenericMethods<C> {
    fun choose(value: C): String = "class"
    fun choose(value: Int): String = "class-int"
    fun <M> convert(context: C, value: M): String = "method"
    fun convert(context: C, value: String): String = "method-string"
}

fun <C, M> genericForward(receiver: GenericMethods<C>, context: C, value: M): String =
    receiver.choose(context) + "/" + receiver.convert(context, value)

fun relay(value: Int): String = if (value <= 0) relay("done") else relay(value - 1)
fun relay(value: String): String = value

class Device {
    fun ordered(first: Int, second: Double): String = "ID"
    fun ordered(first: Double, second: Int): String = "DI"
}

class Effects(var trace: String, var calls: Int) {
    fun receiver(): Device {
        trace = trace + "R"
        calls = calls + 1
        return Device()
    }
    fun integer(): Int {
        trace = trace + "I"
        calls = calls + 1
        return 1
    }
    fun decimal(): Double {
        trace = trace + "D"
        calls = calls + 1
        return 1.0
    }
}

fun arityCase(seed: Int): String = arity() + "/" + beforeDeclaration(seed)
fun numericCase(seed: Int): String = pick(1) + "/" + pick(1.0) + "/" + pick("text") + "/" + pick(seed)
fun memberCase(seed: Int): String {
    val receiver = FinalMethods(0, seed)
    val pick_2 = seed + 1
    val result = receiver.choose(seed) + "/" + receiver.choose(1.0)
    return "$result/${receiver.calls}/${receiver.choose_0}/$pick_2/${pick_0()}"
}
fun genericCase(seed: Int): String = selected(seed) + "/" + forward(seed) + "/" + selected("generic")
fun classGenericCase(seed: Int): String {
    val receiver = GenericMethods<Int>()
    return genericForward(receiver, seed, "text") + "/" + receiver.convert(seed, "text")
}
fun effectsCase(seed: Int): String {
    val effects = Effects("", 0)
    val first = effects.receiver().ordered(effects.integer(), effects.decimal())
    val callback = { effects.receiver().ordered(effects.decimal(), effects.integer()) }
    val second = callback()
    return "$seed/$first/$second/${effects.trace}/${effects.calls}/${relay(2)}"
}
