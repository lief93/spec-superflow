package widgetlazy

fun main() {
    println("item|header")
    listOf("Ada", "Lin").forEachIndexed { index, item ->
        println("values|$index|$item|$index:$item")
    }
    repeat(3) { index -> println("count|$index|$index|$index") }
    emptyList<String>().forEachIndexed { index, item ->
        println("empty|$index|$item|$item")
    }
    arrayOf("R1", "R2").forEachIndexed { index, item ->
        println("row|$index|$item|$item")
    }
}
