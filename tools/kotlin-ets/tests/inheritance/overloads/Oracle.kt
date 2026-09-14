package virtualoverloads

fun main() {
    for (seed in intArrayOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(dispatch(seed))
        println(generic(seed))
        println(defaults(seed))
        println(effects(seed))
        println(numeric(seed))
        println(inherited(seed))
    }
}
