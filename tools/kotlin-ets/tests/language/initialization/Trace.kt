package initialization

var events: String = ""
var count: Int = 0
fun mark(label: String, value: Int): Int { events += label; count++; return value }
fun trace(): String = "$events:$count"
