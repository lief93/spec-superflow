package enums

var trace: Int = 0
fun mark(code: Int): Int { trace = trace * 10 + code / 4; return code }

fun selected(): Stage = Stage.SECOND
fun choose(value: Stage): Int = when (value) {
    Stage.FIRST -> 1
    Stage.SECOND -> 2
    Stage.LAST -> 3
}
fun lookup(name: String): Stage = Stage.valueOf(name)
