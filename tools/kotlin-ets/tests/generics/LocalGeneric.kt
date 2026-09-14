package genericfixture

fun <T> locally(value: T): T {
    fun <U> keep(input: U): U = input
    return keep(value)
}

fun <T> capturedLocal(value: T): T {
    fun keep(): T = value
    return keep()
}

class LocalBox<T>(val value: T) {
    fun read(): T {
        fun keep(): T = value
        return keep()
    }
}

fun scopedLocal(seed: Int): Int {
    val value = seed
    if (seed > 0) {
        val value = seed + 1
        return locally(value)
    }
    return locally(value)
}

fun localCases(seed: Int): String =
    "${locally(seed)}:${capturedLocal("local")}:${LocalBox(seed).read()}:${LocalBox("box").read()}:${scopedLocal(seed)}"
