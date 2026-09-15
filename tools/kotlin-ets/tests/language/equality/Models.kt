package equality

class Identity(val id: Int)

class Key(val id: Int) {
    override fun equals(other: Any?): Boolean = other is Key && id == other.id
    override fun hashCode(): Int = id * 31
}

data class Item(val id: Int, val title: String?) {
    var ignored: Int = 0
}
data class Group(val item: Item, val enabled: Boolean)
data class Metrics(val ratio: Double, val scale: Float, val code: Char) {
    // Formatting floating-point values is outside the equality acceptance cases.
    override fun toString(): String = "Metrics"
}
data class Samples(val values: IntArray)
