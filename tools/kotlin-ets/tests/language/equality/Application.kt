package equality

fun observations(): List<String> {
    val identity = Identity(1)
    val otherIdentity = Identity(1)
    val first = Item(3, "title")
    val equal = Item(3, "title")
    equal.ignored = 99
    val group = Group(first, true)
    val otherGroup = Group(equal, true)
    val key = Key(7)
    val values = intArrayOf(1, 2)
    val samples = Samples(values)
    val metrics = Metrics(1.25, 2.5f, 'x')
    return listOf(
        "${identity === identity}:${identity !== otherIdentity}",
        "${identity == identity}:${identity == otherIdentity}",
        "${first == equal}:${first === equal}:${first != Item(4, "title")}",
        "${sameItem(null, null)}:${sameItem(first, null)}:${sameItem(null, first)}:${sameItem(first, equal)}",
        "${Item(1, null) == Item(1, null)}:${Item(1, null) == Item(1, "x")}",
        "${group == otherGroup}:${group != Group(first, false)}",
        "${first.hashCode()}:${groupHash(group)}:${group.hashCode() == otherGroup.hashCode()}",
        "${key == Key(7)}:${key == Key(8)}:${keyHash(key)}:${key.equals(null)}",
        "${identity.hashCode() == identityHash(identity)}:${identityHash(identity) == identityHash(identity)}",
        "${identity.equals(otherIdentity)}:${identity.equals(identity)}",
        ordered(),
        "${metrics.hashCode()}:${metrics == Metrics(1.25, 2.5f, 'x')}",
        "${Metrics(0.0, 0.0f, 'x') == Metrics(-0.0, 0.0f, 'x')}",
        "${Metrics(0.0 / 0.0, 0.0f / 0.0f, 'x') == Metrics(0.0 / 0.0, 0.0f / 0.0f, 'x')}",
        "${samples == Samples(values)}:${samples == Samples(intArrayOf(1, 2))}:${samples.hashCode()}"
    )
}
