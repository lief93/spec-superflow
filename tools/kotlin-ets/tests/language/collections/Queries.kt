package collectioncases

var starts = 0
fun create(): MutableMap<Key, String?> {
    starts++
    return mutableMapOf(Key(1, "a") to "first", Key(2, "b") to null)
}
val shared = create()
fun replace(values: MutableMap<Key, String?>): String? = values.put(Key(1, "a"), "updated")
fun lookup(values: Map<Key, String?>, id: Int, name: String): String? = values[Key(id, name)]
fun modify(values: MutableSet<Key>): Boolean = values.add(Key(1, "a"))
fun order(values: Map<Key, String?>): String {
    var result = ""
    for ((key, value) in values) result += "${key.id}:$value;"
    return result
}
fun setOrder(values: Set<Int>): Int {
    var result = 0
    for (value in values) result = result * 10 + value
    return result
}
fun pair(): Pair<String, Int> { starts++; return "pair" to 4 }
fun quotient(value: Double): Double = value / value
