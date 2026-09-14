package transitive

inline fun helper(value: Int, action: (Int) -> Int): Int {
    val first = action(value)
    return first + action(value + 1)
}

inline fun helper(value: String, action: (String) -> String): String = action(value)

@PublishedApi
internal fun opaque(value: Int): Int = value + 99

inline fun unused(action: () -> Int): Int = opaque(action())
