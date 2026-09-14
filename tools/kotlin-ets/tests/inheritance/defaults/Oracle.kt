package defaultfixture

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(defaults(seed))
        println(genericDefaults(seed))
        println(closureDefaults(seed))
        println(recursiveDefaults(seed))
        println(nullableDefaults(seed))
        println(bitwiseDefaults(seed))
        println(wideDefaults(seed))
        println(heritageDefaults(seed))
        println(namedEffects(seed))
    }
}
