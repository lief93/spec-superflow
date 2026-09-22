package callbackstate

class CallbackState(var total: Int, var enabled: Boolean)

fun callbackState(seed: Int, firstDelta: Int, secondDelta: Int): String {
    var local = seed
    val state = CallbackState(seed * 2, false)
    val callback: (Int) -> Int = { delta ->
        local += delta
        state.total += local
        state.enabled = state.total > 5
        if (state.enabled && local > seed) {
            local = state.total - 1
        } else {
            local = state.total + 1
        }
        local
    }
    val first = callback(firstDelta)
    val firstState = "$first:${state.total}:${state.enabled}"
    val second = callback(secondDelta)
    return "$firstState|$second:${state.total}:${state.enabled}|$local"
}
