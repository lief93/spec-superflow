package nestedfixture

fun nestedCase(seed: Int): String {
    val original = Node(seed)
    val first = Outer.Node(seed)
    val second = Other.Node(seed)
    first.value += 2
    val generic = Box(Outer.Cell(seed))
    return "${original.read()}|${first.read()}|${second.read()}|${generic.read().read()}|${Other.Cell("text").read()}|${Outer(seed).value}|${Node_0(seed)}|${Local_0(seed)}|${checkedNode(first)}|${checkedNode(original)}"
}

fun checkedNode(value: Any): Int = if (value is Outer.Node) value.read() else -1

fun localCase(seed: Int): String = "${firstLocal(seed)}|${secondLocal(seed)}"

fun readPort(value: Cell<Int>): Int = value.read()

fun identityCase(seed: Int): Int {
    val value = Outer.Node(seed)
    val alias = value
    alias.value += 3
    return value.value
}
