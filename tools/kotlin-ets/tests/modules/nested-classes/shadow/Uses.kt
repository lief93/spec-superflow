package shadowfixture

fun result(Node: Int): Int = Outer.Node(Node).value

fun localResult(seed: Int): Int {
    val Node = seed + 1
    return Outer.Node(Node).value
}

fun initializerResult(seed: Int): Int {
    val Node = Outer.Node(seed)
    return Node.value
}

fun laterBinding(seed: Int): Int {
    val value = Outer.Node(seed)
    val Node = seed + 2
    return value.value + Node
}

fun nestedResult(seed: Int): Int {
    val Node = seed
    if (seed >= 0) {
        val Node = seed + 1
        return Outer.Node(Node).value
    }
    return Outer.Node(Node).value
}

fun closureResult(Node: Int): Int {
    val build = { Outer.Node(Node).value }
    return build()
}

fun checked(Node: Int, value: Any): Int = if (value is Outer.Node) value.value + Node else Node
fun checkedResult(seed: Int): Int = checked(seed, Outer.Node(seed))
fun holderResult(seed: Int): Int = Holder(seed).value
fun unshadowedResult(seed: Int): Int = Another.Node(seed).value

fun unrelated(Safe: Int): Int = Safe + 1
fun siblingResult(seed: Int): Int {
    if (seed < 0) {
        val Safe = seed
        return Safe
    }
    return Outer.Safe(seed).value
}

fun typedOnly(Unique: Int, value: Outer.Unique): Int = Unique + value.value
fun typeOnlyResult(seed: Int): Int = typedOnly(seed, Outer.Unique(seed))
