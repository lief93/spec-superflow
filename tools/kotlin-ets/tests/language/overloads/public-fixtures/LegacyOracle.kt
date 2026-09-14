import languagefixture.legacyTopCase

fun main() {
    for (seed in listOf(0, -3, 7, Int.MIN_VALUE, Int.MAX_VALUE)) {
        println(legacyTopCase(seed))
        println(legacyMemberCase(seed))
    }
}
