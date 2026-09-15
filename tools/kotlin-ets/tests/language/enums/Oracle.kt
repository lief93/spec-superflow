package enums

fun main() {
    for (value in observations()) println(value)
    try { unknown(); println("unexpected") } catch (failure: Throwable) { println(failure.javaClass.simpleName) }
    repeat(2) {
        try { broken(); println("unexpected") } catch (failure: Throwable) { println(failure.javaClass.simpleName) }
    }
}
