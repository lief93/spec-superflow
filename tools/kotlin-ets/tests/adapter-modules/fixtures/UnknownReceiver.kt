package adapterconsumer

import demo.adapters.absolute

fun unsupported(value: Double): Double = "receiver".absolute(value)
