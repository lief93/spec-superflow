package loopfixture

fun main() {
    println(ascending(-2, 2))
    println(ascending(3, 1))
    println(ascending(Int.MAX_VALUE - 1, Int.MAX_VALUE))
    println(ascending(Int.MIN_VALUE, Int.MIN_VALUE + 1))
    println(ascending(Int.MAX_VALUE, Int.MAX_VALUE))
    println(ascending(Int.MIN_VALUE, Int.MIN_VALUE))
    println(exclusive(-2, 2))
    println(exclusive(2, 2))
    println(exclusive(Int.MIN_VALUE, Int.MIN_VALUE))
    println(exclusive(Int.MAX_VALUE - 1, Int.MAX_VALUE))
    println(descending(2, -2))
    println(descending(1, 3))
    println(descending(Int.MIN_VALUE + 1, Int.MIN_VALUE))
    println(descending(Int.MAX_VALUE, Int.MAX_VALUE))
    println(stepped(-7, 8, 3))
    println(stepped(2, 1, 2))
    println(stepped(Int.MIN_VALUE, Int.MAX_VALUE, Int.MAX_VALUE))
    println(stepped(Int.MAX_VALUE, Int.MAX_VALUE, 2))
    println(descendingStep(8, -7, 3))
    println(descendingStep(Int.MAX_VALUE, Int.MIN_VALUE, Int.MAX_VALUE))
    println(descendingStep(Int.MIN_VALUE, Int.MIN_VALUE, 2))
    println(evaluated(-2, 3, 2))
    println(evaluated(3, -2, 2))
    println(nestedFlow(-1, 4))
    println(nestedFlow(Int.MAX_VALUE, Int.MAX_VALUE))
    println(capturedIterations(-1, 2))
    println(capturedIterations(Int.MAX_VALUE - 1, Int.MAX_VALUE))
    println(capturedIterations(Int.MIN_VALUE, Int.MIN_VALUE + 1))
    println(sharedIterations(-1, 2))
    println(sharedIterations(Int.MAX_VALUE - 1, Int.MAX_VALUE))
    println(nativeLoopClosures(3))
    println(nativeLoopClosures(0))
    println(nativeConditionClosure(0))
    println(nativeConditionClosure(1))
    println(nativeConditionClosure(3))
    for (stride in listOf(0, -1, Int.MIN_VALUE)) {
        try {
            println(stepped(3, 1, stride))
        } catch (failure: IllegalArgumentException) {
            println("IllegalArgumentException: ${failure.message}")
        }
    }
}
