package consumer

import transitive.entry

fun scenario(seed: Int): String {
    var count = 0
    var trace = ""
    val result = entry(seed) { value ->
        count += 1
        trace += ":$value"
        value * 7 + count
    }
    return "$result/$count/$trace"
}
