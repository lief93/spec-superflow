package constructorflow

open class FlowBase(val value: Int)
class FlowChild : FlowBase {
    val own: Int
    constructor(seed: Int) : super(seed + 1) { own = seed }
    constructor(seed: Int, alternate: Boolean) : super(seed + 2) { own = seed + 3 }
}
fun constructorResult(mode: Int, seed: Int): Int {
    val child = if (mode == 0) FlowChild(seed) else FlowChild(seed, true)
    return child.value + child.own
}
fun main() {
    for (mode in 0..1) for (seed in listOf(-3, 0, 7)) println(constructorResult(mode, seed))
}
