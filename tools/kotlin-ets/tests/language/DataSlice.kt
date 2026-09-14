package languagefixture

data class Invoice(val item: String, val count: Int = 5) {
    fun increase(amount: Int = 3): Invoice = copy(count = count + amount)
}

fun dataSlice(): String {
    val original = Invoice("blue")
    val changed = original.increase()
    val (item, count) = changed
    return "$original:${changed.count}:$item:$count"
}

fun describe(value: Any): String = if (value is String) value else "other"
fun checked(value: Any): String = value as String
fun safe(value: Any): String? = value as? String

class Named(val label: String) {
    fun valueOf(): Int = 123
    override fun toString(): String = "Named($label)"
}

fun namedLabel(value: Named?): String = "$value"
