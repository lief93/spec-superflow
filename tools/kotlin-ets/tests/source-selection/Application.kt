package selection

val registration = register(1)
val secondRegistration = register(2)
fun register(digit: Int): Int { Journal.value = Journal.value * 10 + digit; return digit }

fun observations(): List<String> {
    val supplier = { defaultValue() }
    val model: Label = Item(supplier())
    return listOf(label(), model.text(), if (Journal.value > 0) positive() else negative(), Journal.value.toString())
}

fun reachableFailure(flag: Boolean): String = if (flag) positive() else unsupported()
fun unsupported(): String = java.lang.System.getProperty("os.name")
fun referenceOnly(): () -> Int = ::defaultValue
