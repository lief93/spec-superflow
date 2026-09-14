package overloadbinary

inline fun helper(value: Double, bias: Int, action: (Double) -> Int): Int = action(value) + bias + 20
