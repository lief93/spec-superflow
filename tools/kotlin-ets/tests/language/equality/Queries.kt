package equality

fun sameItem(left: Item?, right: Item?): Boolean = left == right
fun keyHash(value: Key): Int = value.hashCode()
fun identityHash(value: Identity): Int = value.hashCode()
fun groupHash(value: Group): Int = value.hashCode()
var calls: Int = 0
fun traced(value: Item?): Item? { calls++; return value }
fun ordered(): String {
    calls = 0
    val equal = traced(null) == traced(Item(1, null))
    return "$equal:$calls"
}
