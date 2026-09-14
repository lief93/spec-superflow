package demo.adapters

fun absolute(value: Double): Double = kotlin.math.abs(value)
fun absolute(value: String): String = value
fun String.absolute(value: Double): Double = length + value
fun record(value: String) { println(value) }
