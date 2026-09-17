package smartcast

sealed class Text {
    class Literal(val value: String) : Text()
    class Resource(val resId: Int) : Text()

    fun describe(): String = when (this) {
        is Literal -> value
        is Resource -> "resource:" + resId
    }
}

fun describeOther(text: Text): String = when (text) {
    is Text.Literal -> text.value
    is Text.Resource -> "resource:" + text.resId
}

fun describeThisLiteral(): String = Text.Literal("ok").describe()
fun describeThisResource(): String = Text.Resource(7).describe()
fun describeArgLiteral(): String = describeOther(Text.Literal("x"))
fun describeArgResource(): String = describeOther(Text.Resource(9))
