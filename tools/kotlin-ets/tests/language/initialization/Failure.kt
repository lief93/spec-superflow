package initialization

val crash: Int = fail()
fun fail(): Int = mark("X", 1) / 0
