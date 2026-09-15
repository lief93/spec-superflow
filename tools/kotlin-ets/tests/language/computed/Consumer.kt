package computed

fun readTwice(value: Int): String {
    reset(value)
    val first = score
    val second = score
    return "$first:$second:${snapshot()}"
}

fun update(value: Int, extra: Int): String {
    reset(value)
    val before = score++
    score += extra
    return "$before:${snapshot()}"
}

fun setOnly(value: Int): String {
    score = value
    return snapshot()
}

class PropertyClient {
    fun change(extra: Int): Int {
        val previous = amount++
        amount += extra
        return previous
    }
    fun value(): Int = amount
}

fun storedAccess(value: Int, extra: Int): String {
    resetStored(value)
    val client = PropertyClient()
    val before = client.change(extra)
    setterOnly = value
    getterOnly = extra
    accessor.page = value
    return "$before:${client.value()}:$getterOnly:$setterOnly:${storedTrace()}:${accessor.page}"
}

fun initialSnapshot(): String = "${initialStored()}:${accessor.page}"
