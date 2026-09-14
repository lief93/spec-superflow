package transitive

inline fun entry(value: Int, action: (Int) -> Int): Int = action(value)
