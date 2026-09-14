package defaultconsumer

fun main() {
    for (seed in intArrayOf(1, -2, Int.MAX_VALUE)) {
        val receiver = Box(seed)
        val selected = Box(seed)
        val omitted = defaultIdentity(receiver)
        val explicit = explicitIdentity(receiver, selected)
        check(omitted === receiver && explicit === selected && explicit !== receiver)
        omitted.value += 3
        explicit.value += 4
        check(receiver.value == seed + 3 && selected.value == seed + 4)
        println(scenario(seed))
    }
}
