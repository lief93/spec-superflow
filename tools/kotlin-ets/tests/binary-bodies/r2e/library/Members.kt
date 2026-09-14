package memberbinary

class FinalMember {
    inline fun apply(left: Int, right: Int = 2, action: (Int) -> Int): Int = finish(action(left - right))
    inline fun finish(value: Int): Int = value + 3
    inline fun dependent(left: Int, right: Int = finish(left), action: (Int) -> Int): Int = action(left - right)
    inline fun <T> choose(value: T, fallback: T = value, useFallback: Boolean = false, action: (T) -> T): T =
        relay(action(if (useFallback) fallback else value))
    inline fun <T> relay(value: T): T = value
    inline fun <T> extend(value: T, action: (T) -> T): T = value.selectFrom(action = action)
    inline fun <T> T.selectFrom(fallback: T = this, action: (T) -> T): T = relay(action(fallback))
}

class PeerMember {
    inline fun apply(value: Int): Int = value + 9
}
