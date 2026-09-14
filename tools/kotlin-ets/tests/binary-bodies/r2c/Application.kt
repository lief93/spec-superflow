package defaultconsumer

import defaultbinary.defaultSelect

class Box(var value: Int)

class Effects(var receivers: Int, var callbacks: Int, var defaults: Int, var trace: String) {
    fun receiver(value: Box): Box {
        receivers += 1
        trace += "R"
        return value
    }
    fun number(value: Int): Int {
        receivers += 1
        trace += "N"
        return value
    }
    fun explicit(value: Box): Box {
        trace += "V"
        return value
    }
    fun callback(): () -> Unit {
        callbacks += 1
        trace += "C"
        return {
            defaults += 1
            trace += "D"
        }
    }
}

fun scenario(seed: Int): String {
    val effects = Effects(0, 0, 0, "")
    val first = Box(seed)
    val replacement = Box(seed + 20)
    val omitted = effects.receiver(first).defaultSelect(effects.callback())
    omitted.value += 3
    val explicit = effects.receiver(first).defaultSelect(
        selected = effects.explicit(replacement), mark = effects.callback())
    explicit.value += 4
    val number = effects.number(seed).defaultSelect(effects.callback())
    return "${first.value}/${replacement.value}/$number/${effects.receivers}/${effects.callbacks}/${effects.defaults}/${effects.trace}"
}

fun defaultIdentity(receiver: Box): Box = receiver.defaultSelect({})

fun explicitIdentity(receiver: Box, selected: Box): Box = receiver.defaultSelect(mark = {}, selected = selected)
