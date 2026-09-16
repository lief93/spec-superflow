package datamembers

data class Generic<T>(val value: T)
data class Label(val value: String)
enum class Status { READY }

fun readOnly(): Int = Generic(7).value
fun rendered(): String = Label("kept").toString()
fun interpolated(): String = "label=${Label("kept") }"
fun compared(): Boolean = Label("same") == Label("same")
fun unsupportedGeneric(): String = Generic(7).toString()
fun mixed(): String = "${Status.READY}:${Generic(7).value}:${Label("kept")}"

interface Display { fun text(): String }
class DisplayLabel : Display {
    override fun text(): String = "visible"
    fun text(unused: Int): String = java.lang.System.getProperty("unreachable")
}
fun memberReachability(): String {
    val label: Display = DisplayLabel()
    val values = mapOf(Label("key") to 7)
    return "${label.text()}:${values[Label("key")]}"
}
fun requiredUnsupported(): String = DisplayLabel().text(1)
