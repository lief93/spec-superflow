class OuterDefault(val seed: Int) {
    inner open class Inner { open fun pick(value: Int = seed): Int = value }
}
fun innerDefault(seed: Int): Int = OuterDefault(seed).Inner().pick()
