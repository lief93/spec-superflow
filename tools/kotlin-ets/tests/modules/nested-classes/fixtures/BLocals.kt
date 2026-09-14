package nestedfixture

fun firstLocal(seed: Int): Int {
    class Local(val value: Int) {
        fun read(): Int = value + 1
    }
    return Local(seed).read()
}

fun secondLocal(seed: Int): String {
    class Local<T>(val value: T) {
        fun read(): T = value
    }
    return "${Local(seed).read()}:${Local("local").read()}"
}
