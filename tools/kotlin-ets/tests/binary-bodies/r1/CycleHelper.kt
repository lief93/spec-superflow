package transitive

inline fun helper(value: Int, action: (Int) -> Int): Int = entry(value, action)
