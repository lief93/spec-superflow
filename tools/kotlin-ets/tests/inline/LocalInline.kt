package inlinefixture

inline fun localTwice(value: Int, operation: (Int) -> Int): Int = operation(value) + operation(value + 1)
