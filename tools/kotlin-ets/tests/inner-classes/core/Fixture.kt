package innercore

class Outer(var value: Int) {
    inner class Inner(val extra: Int = value) {
        val initial = value + extra
        fun read(): Int = this@Outer.value + initial
    }
    fun create(): Inner = Inner()
}

fun result(seed: Int): Int = Outer(seed).Inner(2).read()
