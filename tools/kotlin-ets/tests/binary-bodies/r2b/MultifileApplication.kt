package extensionconsumer

import extensionbinary.unsupported

fun multifileScenario(value: Int): Int = value.unsupported { it + 1 }
