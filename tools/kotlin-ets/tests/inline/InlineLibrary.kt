package inlinelibrary

inline fun libraryTransform(first: Int, second: Int = 5, operation: (Int, Int) -> Int): Int {
    val combined = operation(first, second)
    return combined + 7
}

inline fun chooseNonNegative(value: Int, operation: (Int) -> Int): Int {
    if (value < 0) return operation(-value)
    return operation(value) + 2
}
