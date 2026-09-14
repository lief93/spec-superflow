package genericmethods

class PlainBox(var value: Int)
class PlainMethods {
    fun <T> identity(value: T): T = value
}

fun controlCase(seed: Int): String {
    val methods = PlainMethods()
    val original = PlainBox(seed)
    val alias = methods.identity(original)
    original.value = original.value + 1
    return "${methods.identity<Int>(seed)}/${methods.identity("plain")}/${alias.value}"
}
