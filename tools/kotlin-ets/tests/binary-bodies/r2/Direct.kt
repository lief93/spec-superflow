package genericbinary

inline fun <Value : Any, Result : Any> direct(value: Value, action: (Value) -> Result): Result = action(value)
