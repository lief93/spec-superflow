package typecases

fun main() {
    for (value in observations()) println(value)
    try { nullFailure(); println("unexpected") } catch (failure: Throwable) { println(failure.javaClass.simpleName) }
    try { castFailure(); println("unexpected") } catch (failure: Throwable) { println(failure.javaClass.simpleName) }
    try { nullCastFailure(); println("unexpected") } catch (failure: Throwable) { println(failure.javaClass.simpleName) }
}
