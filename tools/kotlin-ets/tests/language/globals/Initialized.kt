package initialized

var calls: Int = 0
fun next(): Int { calls++; return calls }
val initialPage: Int = next()
