package overloadconsumer

import overloadbinary.select

fun selectedDouble(seed: Int): Int = select(seed.toDouble()) { value -> if (value > 0.0) 1 else 2 }
