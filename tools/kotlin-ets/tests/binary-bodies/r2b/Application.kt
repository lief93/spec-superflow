package extensionconsumer

import extensionbinary.extDirect
import extensionbinary.extEntry

class Box(var value: Int)

class Effects(var receivers: Int, var arguments: Int, var trace: String) {
    fun pick(first: Box, second: Box): Box {
        receivers += 1
        trace += "R"
        return if (receivers == 1) first else second
    }
    fun intReceiver(seed: Int): Int {
        receivers += 1
        trace += "N"
        return seed
    }
    fun stamp(value: Int): Int {
        arguments += 1
        trace += "A"
        return value
    }
}

fun scenario(seed: Int): String {
    val effects = Effects(0, 0, "")
    val first = Box(seed)
    val second = Box(seed + 10)
    val direct = effects.pick(first, second).extDirect(effects.stamp(2)) { a, b, stamp ->
        effects.trace += "D"
        a.value += stamp
        b
    }
    direct.value += 5
    val entry = effects.pick(first, second).extEntry(action = { a, b, stamp ->
        effects.trace += "E"
        a.value += stamp
        b
    }, stamp = effects.stamp(3))
    entry.value += 7
    val number = effects.intReceiver(seed).extEntry(effects.stamp(4)) { a, b, stamp ->
        effects.trace += "I"
        a + b + stamp
    }
    return "${first.value}/${second.value}/$number/${effects.receivers}/${effects.arguments}/${effects.trace}/${direct.value}/${entry.value}"
}

fun directIdentity(receiver: Box): Box = receiver.extDirect(1) { a, b, stamp ->
    a.value += stamp
    b
}

fun entryIdentity(receiver: Box): Box = receiver.extEntry(0) { a, b, stamp ->
    a.value += stamp
    b
}
