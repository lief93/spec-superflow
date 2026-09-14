package nullabilityfixture

fun positive(value: Int?): Boolean = value != null && value > 0
fun optionalLength(value: String?): Int? = value?.length
fun safeLength(value: String?): Int = value?.length ?: -1
fun elvisInt(value: Int?, fallback: Int): Int = value ?: fallback
fun nonNullElse(value: Int?): Int = if (value == null) -1 else value
fun safeString(value: String?): String = if (value == null) "<missing>" else value
fun nonEmpty(value: String?): Boolean = value != null && value.length > 0

fun assignedInt(value: Int?): Int {
    if (value != null) {
        val nonNull: Int = value
        return nonNull
    }
    return -1
}

class NullableReader(private val value: Int) {
    fun read(): Int = value
}

fun sourceReceiver(value: NullableReader?): Int = if (value != null) value.read() else -1
fun receiverCase(value: Int?): Int = sourceReceiver(if (value == null) null else NullableReader(value))

class NullableEffects {
    var trace: String = ""
    fun text(value: String?): String? { trace += "S"; return value }
    fun integer(value: Int?): Int? { trace += "I"; return value }
    fun fallback(): Int { trace += "F"; return 7 }
    fun visited(value: Int): Boolean { trace += "V"; return value > 0 }
}

fun safeEffects(value: String?): String {
    val effects = NullableEffects()
    val result = effects.text(value)?.length ?: effects.fallback()
    return "$result:${effects.trace}"
}

fun elvisEffects(value: Int?): String {
    val effects = NullableEffects()
    val result = effects.integer(value) ?: effects.fallback()
    return "$result:${effects.trace}"
}

fun guardEffects(value: Int?): String {
    val effects = NullableEffects()
    val saved = effects.integer(value)
    val result = saved != null && effects.visited(saved)
    return "$result:${effects.trace}"
}
