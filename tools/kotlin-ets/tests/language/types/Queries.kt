package typecases

var calls: Int = 0
fun provide(value: Any?): Any? { calls++; return value }
fun card(value: Any?): Card? = value as? Card
fun title(value: Any?): String = (value as? Named)?.title ?: "missing"
fun force(value: Card?): Card = value!!
fun scalar(value: Any?): String = when {
    value is String -> "text:$value"
    value is Boolean -> "flag:$value"
    else -> "other"
}
