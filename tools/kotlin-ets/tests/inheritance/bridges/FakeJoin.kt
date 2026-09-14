interface InheritedContract<T> {
    fun choose(value: T): String
    fun choose(value: String): String
}
open class ExistingChoice {
    open fun choose(value: String): String = "existing:$value"
}
open class FakeChoice : ExistingChoice(), InheritedContract<String>
class ChildFakeChoice : FakeChoice() {
    override fun choose(value: String): String = "child:$value"
}
class RetainedFakeChoice : FakeChoice()
fun <T> inheritedFirst(owner: InheritedContract<T>, item: T): String = owner.choose(item)
fun <T> inheritedSecond(owner: InheritedContract<T>, item: String): String = owner.choose(item)
fun fakeBridge(seed: Int): String {
    val owner = FakeChoice()
    return inheritedFirst(owner, "$seed") + ":" + inheritedSecond(owner, "done") + ":" + owner.choose("direct")
}

interface GenericInherited<T> {
    fun select(value: T): T
    fun select(value: String): T
}
open class GenericExisting<T> {
    open fun select(value: T): T = value
}
class GenericFake : GenericExisting<String>(), GenericInherited<String>
fun <T> genericInheritedFirst(owner: GenericInherited<T>, value: T): T = owner.select(value)
fun <T> genericInheritedSecond(owner: GenericInherited<T>, value: String): T = owner.select(value)
fun inheritedComposition(seed: Int): String {
    val child: FakeChoice = ChildFakeChoice()
    val retained = RetainedFakeChoice()
    val generic = GenericFake()
    return inheritedFirst(child, "$seed") + ":" + inheritedSecond(child, "x") + ":" + child.choose("direct") + ":" +
        inheritedFirst(retained, "a") + ":" + inheritedSecond(retained, "b") + ":" +
        genericInheritedFirst(generic, "c") + ":" + genericInheritedSecond(generic, "d") + ":" + generic.select("e")
}
