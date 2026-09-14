package memberconsumer

fun main() {
    for (seed in listOf(1, -2, 2147483647)) {
        println(scenario(memberbinary.FinalMember(), memberbinary.PeerMember(), seed))
    }
}
