package overloadbinary

inline fun select(value: Double, bias: Int = 5, action: (Double) -> Int): Int = helper(value, bias, action) + 200
