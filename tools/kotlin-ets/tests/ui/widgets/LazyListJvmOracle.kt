package widgetlazy

fun main() {
    var columnIndex = 1
    var rowIndex = 1
    println("state|column|$columnIndex|6")
    println("state|row|$rowIndex|4")
    columnIndex = 3
    rowIndex = 0
    println("visible|column|$columnIndex")
    println("visible|row|$rowIndex")
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
