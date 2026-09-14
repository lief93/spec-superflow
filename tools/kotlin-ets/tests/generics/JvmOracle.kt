package genericfixture

fun main() {
    for (seed in listOf(-7, 0, 3, 29)) {
        println(functionCases(seed))
        println(classCases(seed))
        println(localCases(seed))
    }
}
