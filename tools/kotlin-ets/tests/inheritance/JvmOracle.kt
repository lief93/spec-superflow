package inheritancefixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(dispatch(seed))
        println(abstractDispatch(seed))
        println(callEffects(seed))
        println(constructorEffects(seed))
        println(selected(true, seed))
        println(selected(false, seed))
        println(propertyDispatch(seed))
    }
}
