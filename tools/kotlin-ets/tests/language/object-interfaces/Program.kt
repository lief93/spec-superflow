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

sealed class Command {
    fun label(): String = "complete"

    object Complete : Command()
}

fun defaultEvent(): String = State().event.label()
fun triggeredEvent(): String = State(Triggered("hello")).event.label()
fun sameInstance(): Boolean {
    val first: Event<String> = Consumed
    val second: Event<Int> = Consumed
    return first === second
}

fun sealedObjectLabel(): String = Command.Complete.label()
fun sealedObjectIdentity(): Boolean {
    val first: Command = Command.Complete
    val second: Command = Command.Complete
    return first === second
}
