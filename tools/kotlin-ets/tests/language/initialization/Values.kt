package initialization

val first: Int = mark("A", seed)
val model: Model = Model(first + 3)
val choices: List<Int> = listOf(first, first + 1)
val doubled: Int = compute()
var score: Int = mark("B", 4)
    get() = field + 1
    set(next) { field = next * 2 }
val optional: String? = if (first > 0) null else "present"

fun compute(): Int = mark("C", first * 2)
fun untouched(): Int = 7
fun withDefault(value: Int = mark("E", 9)): Int = value
fun snapshot(): String = "$first:${model.value}:${choices[1]}:$doubled:$score:${optional ?: "none"}"
