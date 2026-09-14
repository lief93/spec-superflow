package genericconsumer

import genericbinary.direct
import genericbinary.entry

class Box(var value: Int)

class Effects(var count: Int, var trace: String) {
    fun intValue(value: Int): Int {
        count += 1
        trace += "I"
        return value
    }
    fun boxValue(value: Box): Box {
        count += 1
        trace += "B"
        return value
    }
}

fun scenario(seed: Int): String {
    val effects = Effects(0, "")
    val first = direct(effects.intValue(seed)) { value ->
        effects.count += 1
        effects.trace += "D"
        value + 2
    }
    val box = Box(seed)
    val second = entry(action = { value: Box ->
        effects.count += 1
        effects.trace += "O"
        value.value += effects.count
        value
    }, value = effects.boxValue(box))
    val third = entry(effects.intValue(first)) { value ->
        effects.count += 1
        effects.trace += "G"
        value * 3
    }
    return "$first/${second.value}/${box.value}/$third/${effects.count}/${effects.trace}"
}
