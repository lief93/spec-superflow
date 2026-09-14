package languagefixture

object InitTrace {
    var starts: Int = 0
}

object VisitCounter {
    var visits: Int = seedVisits()
    fun add(amount: Int = 2): Int {
        visits += amount
        return visits
    }
}

fun seedVisits(): Int {
    InitTrace.starts += 1
    return 3
}

fun singletonInitCount(): Int = InitTrace.starts

fun singletonSlice(): Int {
    val first = VisitCounter
    val second = VisitCounter
    first.add()
    return second.add(4)
}
