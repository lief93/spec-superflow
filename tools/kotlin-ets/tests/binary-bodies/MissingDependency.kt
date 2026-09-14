package binarylibrary

@PublishedApi
internal fun hiddenOffset(value: Int): Int = value + 17

inline fun binaryTransform(first: Int, second: Int = 5, operation: (Int, Int) -> Int): Int =
    hiddenOffset(operation(first, second))
