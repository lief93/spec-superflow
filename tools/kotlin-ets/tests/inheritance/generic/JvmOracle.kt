package genericheritage

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(genericDispatch(seed))
        println(parameterized(seed))
        println(nestedArguments(seed))
        println(stringDispatch(seed))
        println(constructorEffects(seed))
        println(genericCaller(seed))
    }
    println(migratedGeneric())
}
