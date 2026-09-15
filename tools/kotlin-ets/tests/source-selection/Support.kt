package selection

val supportRegistration = initializeSupport()
fun initializeSupport(): Int { Journal.value = Journal.value * 10 + 3; return 3 }
fun defaultValue(): Int = 4
fun label(value: Int = defaultValue()): String = "label:$value"
fun label(value: String): String = java.lang.System.getProperty(value)
fun positive(): String = "positive"
fun negative(): String = "negative"

object Journal { var value = 0 }
