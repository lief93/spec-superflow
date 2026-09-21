package klibclosure

fun main() {
    val values = listOf(1, 2, 3, 4)
    println(scenario("filter", values))
    println(scenario("map", values))
    println(scenario("first", values))
    println(scenario("first", emptyList()))
}
