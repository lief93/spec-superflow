package selection

val modelFileRegistration = java.lang.System.getProperty("os.name")
interface Label { fun text(): String }
class Item(val value: Int): Label { override fun text(): String = "item:$value" }
