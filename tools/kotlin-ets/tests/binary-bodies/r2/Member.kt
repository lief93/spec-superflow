package genericbinary

class Member {
    inline fun <Value : Any> unsupported(value: Value, action: (Value) -> Value): Value = action(value)
}
