package declarationvariance

fun main() {
    for (seed in intArrayOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(covariance(seed))
        println(contravariance(seed))
        println(nested(seed))
        println(property(seed))
        println(mixed(seed))
        println(nullable(seed))
    }
}
