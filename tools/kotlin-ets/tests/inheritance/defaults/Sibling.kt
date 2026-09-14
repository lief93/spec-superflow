package defaultfixture

class RestrictedSibling(value: Int, effects: Effects) : RestrictedBase<Int>(value, effects) {
    public override fun choose(first: Int, second: Int): Int {
        effects.number("S", 1)
        return first + second
    }
}
