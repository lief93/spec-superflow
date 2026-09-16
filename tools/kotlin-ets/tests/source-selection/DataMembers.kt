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
