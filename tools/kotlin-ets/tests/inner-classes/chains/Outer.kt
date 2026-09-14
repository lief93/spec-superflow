package innerchains

class Outer(var value: Int) {
    var log: String = ""
    fun mark(label: String, value: Int): Int { log += label; return value }
    fun select(): Outer { log += "O"; return this }
    inner class Inner(var value: Int) {
        val `this$0`: Int = 30
        fun select(): Inner { log += "R"; return this }
        fun make(Deep: Int): Deep = Deep(Deep, 2)
        inner class Deep(val first: Int = mark("D", value), val second: Int = mark("E", this@Outer.value)) {
            val `this$0`: Int = 40
            val initial = mark("P", first + this@Inner.value + this@Outer.value)
            init { mark("I", second) }
            fun owner(): Inner = this@Inner
            fun root(): Outer = this@Outer
            fun add(amount: Int) { this@Inner.value += amount; this@Outer.value += amount + 1 }
            fun read(): String = "$first:$second:$initial:${this@Inner.value}:${this@Outer.value}:$log"
            inner class Leaf {
                fun add(amount: Int) { this@Inner.value += amount; this@Outer.value += amount }
                fun read(): String = "${this@Deep.first}:${this@Inner.value}:${this@Outer.value}"
            }
        }
    }
}

class Deep(val value: Int)
