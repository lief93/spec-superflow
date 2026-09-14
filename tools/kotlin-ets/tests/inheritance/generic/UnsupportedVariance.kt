interface Variant<out T> { fun read(): T }
class VariantText : Variant<String> { override fun read(): String = "text" }
