package adapterconsumer

import demo.adapters.absolute
import demo.adapters.record

fun magnitude(value: Double): Double = absolute(value)
fun report(value: String) {
    record(value)
    record("adapter:end")
}
