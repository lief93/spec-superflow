package extensionconsumer

fun memberScenario(receiver: extensionbinary.Member, value: Int): Int = receiver.unsupported(value) { it + 1 }
