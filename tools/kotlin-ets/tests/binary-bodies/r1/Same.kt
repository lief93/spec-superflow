package transitive

inline fun entry(value: Int, action: (Int) -> Int): Int = helper(value, action) + 3

inline fun helper(value: Int, action: (Int) -> Int): Int {
    val first = action(value)
    return first + action(value + 1)
}
