open class OpenJoined : Joined<String> {
    override fun choose(value: String): String = "open:$value"
}
class ChildJoined : OpenJoined() {
    override fun choose(value: String): String = "child:$value"
}
class InheritedJoined : OpenJoined()
abstract class AbstractJoined : Joined<String> {
    abstract override fun choose(value: String): String
}
class ConcreteJoined : AbstractJoined() {
    override fun choose(value: String): String = "concrete:$value"
}
abstract class BareJoined : Joined<String>
class BareConcrete : BareJoined() {
    override fun choose(value: String): String = "bare:$value"
}
fun bareBridge(seed: Int): String {
    val owner: BareJoined = BareConcrete()
    return pick(owner, "$seed") + ":" + fixed(owner, "done")
}

fun <T> fixed(value: Joined<T>, item: String): String = value.choose(item)
fun inheritedBridge(seed: Int): String {
    val child: OpenJoined = ChildJoined()
    val inherited: Joined<String> = InheritedJoined()
    val abstract: AbstractJoined = ConcreteJoined()
    return pick(child, "$seed") + ":" + fixed(child, "$seed") + ":" +
        pick(inherited, "a") + ":" + fixed(inherited, "b") + ":" +
        pick(abstract, "c") + ":" + fixed(abstract, "d")
}

fun bridgeEffects(seed: Int): String {
    var trace = ""
    val receiver = { trace += "R"; ChildJoined() }
    val argument = { trace += "A"; "$seed" }
    val first = pick(receiver(), argument())
    val second = fixed(receiver(), argument())
    return "$first:$second:$trace"
}

interface Sink<T> {
    fun accept(value: T)
    fun accept(value: String)
}
class TextSink : Sink<String> {
    var text: String = ""
    override fun accept(value: String) { text += value }
}
fun <T> send(sink: Sink<T>, value: T) { sink.accept(value) }
fun <T> fixedSend(sink: Sink<T>, value: String) { sink.accept(value) }
fun voidBridge(seed: Int): String {
    val sink = TextSink()
    send(sink, "$seed")
    fixedSend(sink, ":done")
    return sink.text
}

interface GenericJoined<T> {
    fun <V> select(value: T, extra: V): V
    fun <W> select(value: String, extra: W): W
}
class GenericText : GenericJoined<String> {
    override fun <R> select(value: String, extra: R): R = extra
}
fun <T, V> genericFirst(owner: GenericJoined<T>, value: T, extra: V): V = owner.select(value, extra)
fun <T, V> genericSecond(owner: GenericJoined<T>, value: String, extra: V): V = owner.select(value, extra)
fun genericBridge(seed: Int): String {
    val owner = GenericText()
    val missing: String? = null
    return "${genericFirst(owner, "x", seed)}:${genericSecond(owner, "x", "done")}:${genericSecond(owner, "x", missing)}"
}

interface NullableJoined<T> {
    fun select(value: T): String
    fun select(value: String?): String
}
class NullableText : NullableJoined<String?> {
    override fun select(value: String?): String = value ?: "null"
}
fun <T> nullableFirst(owner: NullableJoined<T>, value: T): String = owner.select(value)
fun <T> nullableSecond(owner: NullableJoined<T>, value: String?): String = owner.select(value)
fun nullableBridge(seed: Int): String {
    val owner = NullableText()
    return nullableFirst(owner, null) + ":" + nullableSecond(owner, null) + ":" + nullableSecond(owner, "$seed")
}
