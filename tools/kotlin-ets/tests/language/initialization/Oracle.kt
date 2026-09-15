package initialization

fun main(args: Array<String>) {
    println(before())
    if (args[0] == "failure" || args[0] == "nestedFailure") {
        repeat(2) {
            try { println(if (args[0] == "failure") readFailure() else readOuterFailure()) }
            catch (failure: Throwable) { println(failure.javaClass.simpleName) }
            println(before())
        }
    } else {
        println(when (args[0]) {
            "method" -> methodFirst()
            "property" -> propertyFirst()
            "default" -> defaultFirst()
            else -> writeFirst(8)
        })
        println(methodFirst())
        println(writeFirst(3))
        println(propertyFirst())
        println(legacyInitializer())
    }
}
