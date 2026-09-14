package extensionbinary

inline fun <Input : Any, Result : Any> Input.extEntry(stamp: Int, action: (Input, Input, Int) -> Result): Result =
    this.extHelper(stamp, action)
