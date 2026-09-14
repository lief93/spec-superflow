package memberbinary

class FinalMember {
    inline fun apply(left: Int, right: Int = 2, action: (Int) -> Int): Int = finish(action(left - right))
    inline fun finish(value: Int): Int = value + 3
    inline fun dependent(left: Int, right: Int = finish(left), action: (Int) -> Int): Int = action(left - right)
}

class PeerMember {
    inline fun apply(value: Int): Int = value + 9
}
