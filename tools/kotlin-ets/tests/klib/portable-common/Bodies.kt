package portablecommon

// Equivalent pure Kotlin bodies for the ascending, unit-step IntRange slice.
// The termination order follows common IntProgressionIterator.nextInt: do not
// increment the final element (in particular Int.MAX_VALUE).
class IntSpan(val first: Int, val last: Int) {
    operator fun iterator(): IntCursor = IntCursor(first, last)
}

class IntCursor(first: Int, private val last: Int) {
    private var available: Boolean = first <= last
    private var nextValue: Int = if (available) first else last

    operator fun hasNext(): Boolean = available

    operator fun next(): Int {
        val value = nextValue
        if (value == last) {
            if (!available) exhausted()
            available = false
        } else {
            nextValue = value + 1
        }
        return value
    }
}

// Equivalent to the common Iterable.map loop, with its allocation/append
// actual boundary explicit. This is deliberately non-inline: linked bodies
// and ordinary generic function calls must survive into the ETS output.
fun <R> IntSpan.mapBody(transform: (Int) -> R): List<R> {
    val result = newList<R>()
    for (item in this) append(result, transform(item))
    return result
}
