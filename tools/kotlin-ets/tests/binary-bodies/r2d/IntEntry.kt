package overloadbinary

inline fun select(value: Int, bias: Int = 3, action: (Int) -> Int): Int = helper(value, bias, action) + 100
