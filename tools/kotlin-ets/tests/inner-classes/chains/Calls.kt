package innerchains

fun typed(value: Outer.Inner.Deep): Outer.Inner = value.owner()

fun sharing(seed: Int): String {
    val outer = Outer(seed)
    val other = Outer(seed + 100)
    val parent = outer.Inner(10)
    val sibling = outer.Inner(20)
    val a = parent.Deep(1, 2)
    val b = parent.Deep(3, 4)
    val c = sibling.Deep(5, 6)
    val d = other.Inner(30).Deep(7, 8)
    a.add(2)
    typed(a).value += 3
    b.root().value += 4
    return "${a.read()}|${b.read()}|${c.read()}|${d.read()}|${outer.value}:${other.value}"
}

fun order(seed: Int): String {
    val outer = Outer(seed)
    val parent = outer.select().Inner(outer.mark("N", 10))
    val a = parent.select().Deep(second = outer.mark("B", 2), first = outer.mark("A", 1))
    val before = a.read()
    val b = parent.select().Deep()
    val middle = b.read()
    val c = parent.select().Deep(first = outer.mark("F", 3))
    return "$before|$middle|${c.read()}|${outer.log}"
}

fun names(seed: Int): String {
    val parent = Outer(seed).Inner(4)
    val a = parent.make(5)
    val b = Peer(seed).Inner(6).Deep(7)
    val Deep = 8
    val c = parent.Deep(Deep, 9)
    return "${a.read()}|${b.read()}|${c.first}|${parent.`this$0`}:${a.`this$0`}|${innerchains.Deep(seed).value}"
}

fun depth(seed: Int): String {
    val parent = Outer(seed).Inner(5)
    val deep = parent.Deep(1, 2)
    val a = deep.Leaf()
    val b = deep.Leaf()
    a.add(3)
    return "${a.read()}|${b.read()}|${deep.read()}"
}

fun cases(seed: Int): String = "${sharing(seed)}\n${order(seed)}\n${names(seed)}\n${depth(seed)}"
