package supercases

fun observations(): List<String> {
    trace = ""
    val child = Child(3)
    val model = query(child)
    val first = "${model.value}:$trace"
    child.amount = 5
    return listOf(first, "${child.amount}:$trace", "${Middle(3).result(2).value}", "${child.baseSeed()}")
}
