package defaultcases

fun observations(): List<String> {
    val first = Default()
    val child = Child()
    val ordinary = query(first, 2)
    val inherited = query(child, 2)
    val overridden = query(Override(), 2)
    val mapValue = lookup(ordinary)!!
    val failure = try { lookup(inherited)!!.ordinal } catch (error: NullPointerException) { -1 }
    val counter: Counter = CounterValue(3)
    counter.add(4)
    return listOf("${ordinary.value}:${inherited.value}:${overridden.value}",
        "${first.value}:${child.rank()}:${child.stage().name}",
        "${mapValue.name}:$failure:${ordinary == Model(5)}", "${first.model(4).value}",
        "${query(GrandChild(), 2).value}:${GrandChild().value}", "${counter.total}")
}
