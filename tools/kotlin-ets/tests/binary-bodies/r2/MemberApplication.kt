package genericconsumer

fun memberScenario(receiver: genericbinary.Member, value: Int): Int = receiver.unsupported(value) { it + 1 }
