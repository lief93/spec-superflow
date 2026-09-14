package modulefixture

fun main() {
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(describe(value))
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) {
        println(entryLocalValue(value))
        println(numbersLocalValue(value))
    }
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(privateClassValue(value))
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(crossFileInlineValue(value))
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(crossFileInlineGeneric(value))
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(crossFileInlineDefault(value))
    for (value in listOf(-2, 0, 41, Int.MAX_VALUE)) println(crossFileInlineOverloaded(value))
}
