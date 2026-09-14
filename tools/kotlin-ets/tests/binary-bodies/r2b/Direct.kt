package extensionbinary

inline fun <Value : Any, Result : Any> Value.extDirect(stamp: Int, action: (Value, Value, Int) -> Result): Result =
    action(this, this, stamp)
