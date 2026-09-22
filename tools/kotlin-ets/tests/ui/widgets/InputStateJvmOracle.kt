package widgetstateinput

private data class State(val loading: Boolean, val error: String?, val content: String)

fun main() {
    val inputs = listOf(
        State(true, null, "ignored"),
        State(false, "failed", "ignored"),
        State(false, null, "ready"),
    )
    inputs.forEach { state ->
        val effects = mutableListOf<String>()
        val branch = when {
            state.loading -> "loading"
            state.error != null -> "error".also { effects += "retry" }
            else -> "content".also { effects += "refresh" }
        }
        println("$branch|${effects.joinToString()}")
    }
}
