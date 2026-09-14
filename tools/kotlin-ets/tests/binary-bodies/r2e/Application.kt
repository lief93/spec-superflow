package memberconsumer

import memberbinary.FinalMember
import memberbinary.PeerMember

class Effects(var count: Int, var trace: String) {
    fun receiver(value: FinalMember): FinalMember {
        count += 1
        trace += "R"
        return value
    }

    fun value(value: Int, label: String): Int {
        count += 1
        trace += label
        return value
    }
}

fun scenario(receiver: FinalMember, peer: PeerMember, seed: Int): String {
    val effects = Effects(0, "")
    val first = effects.receiver(receiver).apply(
        action = { value ->
            effects.count += 1
            effects.trace += "L"
            value * 2
        },
        right = effects.value(seed + 1, "B"),
        left = effects.value(seed, "A")
    )
    val second = effects.receiver(receiver).apply(left = effects.value(first, "C")) { value ->
        effects.count += 1
        effects.trace += "D"
        value + 5
    }
    val third = peer.apply(effects.value(seed, "P"))
    val fourth = effects.receiver(receiver).dependent(left = effects.value(seed, "E")) { value ->
        effects.count += 1
        effects.trace += "F"
        value + 10
    }
    val fifth = effects.receiver(receiver).dependent(
        right = effects.value(seed + 2, "H"),
        left = effects.value(seed, "G")
    ) { value ->
        effects.count += 1
        effects.trace += "I"
        value * 3
    }
    val sixth = effects.receiver(receiver).choose(value = effects.value(seed, "J")) { value ->
        effects.count += 1
        effects.trace += "K"
        value + 2
    }
    val seventh = receiver.choose<String?>(value = null, fallback = "fallback", useFallback = true) { it }
    val eighth = receiver.choose(value = "text") { it }
    return "$first/$second/$third/$fourth/$fifth/$sixth/$seventh/$eighth/${effects.count}/${effects.trace}"
}
