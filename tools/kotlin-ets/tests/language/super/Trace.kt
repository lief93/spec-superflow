package supercases

var trace = ""
fun mark(value: String) { trace += value }
fun argument(value: Int): Int { mark("a$value"); return value }
