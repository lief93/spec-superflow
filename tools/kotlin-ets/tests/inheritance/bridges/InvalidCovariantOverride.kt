open class InvalidNumericBase { open fun read(): Int = 1 }
class InvalidNumericChild : InvalidNumericBase() { override fun read(): Double = 1.0 }
open class InvalidNullableBase { open fun read(): String = "base" }
class InvalidNullableChild : InvalidNullableBase() { override fun read(): String? = null }
interface InvalidGenericBase { fun <T> read(value: T): T }
class InvalidGenericChild : InvalidGenericBase {
    override fun <T> read(value: T): String = "wrong"
}
