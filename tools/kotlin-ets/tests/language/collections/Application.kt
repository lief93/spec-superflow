package collectioncases

fun observations(): List<String> {
    val data = shared
    val before = "${starts}:${lookup(data, 1, "a")}:${data.size}"
    val previous = replace(data)
    val present = "${data.containsKey(Key(2, "b"))}:${data.containsKey(Key(3, "c"))}:${lookup(data, 2, "b") == null}"
    data[Key(3, "c")] = "third"
    val traversal = order(data)
    val removed = data.remove(Key(1, "a"))
    data[Key(1, "a")] = "again"
    val collisions = mutableMapOf(Collision(1) to 10, Collision(2) to 20)
    val collisionBefore = "${collisions[Collision(1)]}:${collisions[Collision(2)]}:${collisions.size}"
    collisions.remove(Collision(1))
    val keys = mutableSetOf(Key(1, "a"), Key(1, "a"), Key(2, "b"))
    val duplicate = modify(keys)
    val keyRemoved = keys.remove(Key(2, "b"))
    val identity = Identity()
    val identities = setOf(identity, identity, Identity())
    val stages = mapOf(Stage.FIRST to "first", Stage.LAST to "last")
    val nullable = mutableMapOf<String?, Int?>(null to null, "x" to 2)
    val nullPresent = nullable.containsKey(null)
    val nullRemoved = nullable.remove(null)
    val empty = mutableSetOf<Int>()
    empty.add(3)
    empty.add(1)
    empty.add(3)
    val sequence = setOrder(empty)
    empty.clear()
    val pairs = mapOf<String?, Int?>(pair())
    val members = setOf(Collision(1), Collision(2), Collision(1))
    val nan = quotient(0.0)
    val scalars = setOf(0.0, -0.0, nan, nan)
    val chars = setOf('a', 'a', 'b')
    val nulls = setOf<Int?>(null, 1, null)
    return listOf(before, "$previous:$present", traversal, "$removed:${order(data)}:$starts",
        "$collisionBefore:${collisions[Collision(2)]}:${collisions.size}",
        "${keys.size}:$duplicate:$keyRemoved:${keys.contains(Key(1, "a"))}",
        "${identities.size}:${identities.contains(identity)}:${identities.contains(Identity())}",
        "${stages[Stage.LAST]}:${setOf(Stage.FIRST, Stage.FIRST).size}",
        "$nullPresent:${nullRemoved == null}:${nullable.containsKey(null)}:${nullable.size}",
        "$sequence:${empty.isEmpty()}:${mapOf<Int, String>().isEmpty()}",
        "${pairs["pair"]}:$starts:${pairs.containsValue(4)}:${pairs.containsValue(null)}",
        "${members.size}:${members.contains(Collision(2))}:${scalars.size}:${scalars.contains(-0.0)}:${chars.size}:${nulls.size}")
}
