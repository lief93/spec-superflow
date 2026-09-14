package transitive

inline fun entry(value: Int, action: (Int) -> Int): Int = helper(value, action) + 3
