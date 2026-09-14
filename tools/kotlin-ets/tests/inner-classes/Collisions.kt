package innerfixture

fun `this$0`(value: Int): Int = value
fun `this$0`(value: String): Int = 10

class Clash(val value: Int) {
    inner class Item(val `this$0`: Int, val `this$0_0`: Int) {
        val initial = this@Clash.value + `this$0`("text")
        fun read(): Int = initial + this@Clash.value + `this$0` + `this$0_0`
    }
}
