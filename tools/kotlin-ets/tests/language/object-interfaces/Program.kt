package objectinterfaces

sealed interface Event<out T> {
    fun label(): String
}

object Consumed : Event<Nothing> {
    override fun label(): String = "consumed"
}

class Triggered<T>(val content: T) : Event<T> {
    override fun label(): String = "triggered"
}

class State(val event: Event<String> = Consumed)

fun defaultEvent(): String = State().event.label()
fun triggeredEvent(): String = State(Triggered("hello")).event.label()
fun sameInstance(): Boolean {
    val first: Event<String> = Consumed
    val second: Event<Int> = Consumed
    return first === second
}
