package genericbinary

inline fun <Input : Any, Result : Any> entry(value: Input, action: (Input) -> Result): Result = helper(value, action)
