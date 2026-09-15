package models

class Other {
    fun isNotEmpty(): Boolean = false
    fun isEmpty(): Boolean = true
}

var evaluations: Int = 0

fun produce(values: List<Int>): List<Int> { evaluations++; return values }

fun receiverValue(): Int { evaluations = evaluations * 10 + 1; return 4 }
fun callbackValue(): (Int) -> Int {
    evaluations = evaluations * 10 + 2
    return { value -> evaluations = evaluations * 10 + 3; value + 1 }
}

fun evaluationOrder(): String {
    evaluations = 0
    val result = receiverValue().let(callbackValue())
    val order = evaluations
    evaluations = 0
    val values = listOf(1, 2)
    val nonempty = produce(values).isNotEmpty()
    val empty = produce(values).isEmpty()
    return "$result:$order:$nonempty:$empty:$evaluations"
}

fun nullableLet(value: String?): String {
    var calls = 0
    val label = value?.let { calls++; it } ?: "fallback"
    value.let { calls++ }
    return "$label:$calls"
}

fun <T> relay(value: T): T = value

fun guardedGeneric(value: String?): String =
    if (value != null) relay(value) else "missing"

fun nullableGeneric(value: String?): String = relay(value) ?: "missing"

fun emptinessCheck(present: Boolean): String {
    val mutable = mutableListOf<Int>()
    if (present) mutable.add(1)
    val values: List<Int> = mutable
    val collection: Collection<Int> = mutable
    return "${mutable.isEmpty()}:${mutable.isNotEmpty()}:${values.isEmpty()}:${values.isNotEmpty()}:" +
        "${collection.isEmpty()}:${collection.isNotEmpty()}:${Other().isEmpty()}:${Other().isNotEmpty()}"
}
