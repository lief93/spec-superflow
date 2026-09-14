package innerfixture

class Outer(var value: Int) {
    var log: String = ""
    fun mark(label: String, value: Int): Int {
        log += label
        return value
    }
    fun select(): Outer {
        log += "R"
        return this
    }
    inner class Item(val first: Int = mark("D", value), val second: Int = mark("E", value + 1)) {
        val initial = mark("P", first + this@Outer.value)
        init { mark("I", second) }
        fun read(): String = "$first:$second:$initial:${this@Outer.value}:$log"
        fun add(amount: Int) { this@Outer.value += amount }
        fun owner(): Outer = this@Outer
    }
}

class Item(val value: Int)

class PrivateOwner(val value: Int) {
    private inner class Hidden {
        fun read(): Int = this@PrivateOwner.value
    }
    fun read(): Int = Hidden().read()
}
