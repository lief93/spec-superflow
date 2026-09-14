package overloadbinary

inline fun helper(value: Int, bias: Int, action: (Int) -> Int): Int = action(value) + bias + 10
