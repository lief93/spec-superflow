interface Joined<T> {
    fun choose(value: T): String
    fun choose(value: String): String
}
class JoinedText : Joined<String> {
    override fun choose(value: String): String = "text:$value"
}
class JoinedInt : Joined<Int> {
    override fun choose(value: Int): String = "int:$value"
    override fun choose(value: String): String = "other:$value"
}
fun <T> pick(value: Joined<T>, item: T): String = value.choose(item)
fun bridgeJoin(): String = pick(JoinedText(), "x") + ":" + pick(JoinedInt(), 7) + ":" + JoinedInt().choose("a")
