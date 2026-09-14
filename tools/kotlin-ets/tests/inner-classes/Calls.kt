package innerfixture

fun identityCase(seed: Int): String {
    val first = Outer(seed)
    val second = Outer(seed + 100)
    val a = first.Item(1, 2)
    val b = first.Item(3, 4)
    val c = second.Item(5, 6)
    a.owner().value += 11
    a.add(7)
    return "${first.value}|${second.value}|${b.owner().value}|${a.read()}|${b.read()}|${c.read()}"
}

fun orderCase(seed: Int): String {
    val outer = Outer(seed)
    val named = outer.select().Item(second = outer.mark("B", seed + 2), first = outer.mark("A", seed + 1))
    val first = named.read()
    val defaults = outer.select().Item()
    val second = defaults.read()
    val partial = outer.select().Item(first = outer.mark("F", seed + 3))
    return "$first|$second|${partial.read()}|${outer.log}"
}

fun collisionCase(seed: Int): String {
    val outer = Clash(seed)
    val a = outer.Item(1, 2)
    val b = outer.Item(3, 4)
    return "${a.read()}|${b.read()}|${a.`this$0`}|${a.`this$0_0`}|${Item(seed).value}"
}

fun cases(seed: Int): String =
    "${identityCase(seed)}\n${orderCase(seed)}\n${collisionCase(seed)}\n${PrivateOwner(seed).read()}"
