package conversionnegative

class Lookalike { fun toDouble(): Double = 1.0 }
fun floating(value: Float): Double = value.toDouble()
fun wide(value: Long): Double = value.toDouble()
fun alreadyDouble(value: Double): Double = value.toDouble()
fun abstractNumber(value: Number): Double = value.toDouble()
fun sourceMethod(value: Lookalike): Double = value.toDouble()
