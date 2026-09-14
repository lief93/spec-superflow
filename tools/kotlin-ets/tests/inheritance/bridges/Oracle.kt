fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(bridgeJoin())
        println(inheritedBridge(seed))
        println(bridgeEffects(seed))
        println(voidBridge(seed))
        println(genericBridge(seed))
        println(nullableBridge(seed))
        println(fakeBridge(seed))
        println(inheritedComposition(seed))
        println(bareBridge(seed))
    }
}
