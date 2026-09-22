package themeprojection

fun main() {
    check(!supportsDynamicTheming())
    println(platformFallbackLabel())
}
