package binarylibrary

inline fun binaryTransform(first: Int, second: Int = 5, operation: (Int, Int) -> Int): Int {
    val combined = operation(first, second)
    return combined + 7
}
