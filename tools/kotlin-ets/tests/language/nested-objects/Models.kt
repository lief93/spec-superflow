package nestedobjects

var initialized = 0

class First {
    companion object {
        fun label(value: Int): String = "first:${Settings.seed}:$value"
    }
    object Settings {
        val seed = nextSeed()
        var value = 3
    }
}

class Second {
    companion object {
        private val prefix = "second"
        fun label(value: Int): String = "$prefix:${Settings.seed}:$value"
    }
    object Settings { val seed = nextSeed() }
}

enum class State {
    READY, DONE;
    companion object {
        fun select(finished: Boolean): State = if (finished) DONE else READY
    }
}

fun nextSeed(): Int {
    initialized += 1
    return initialized
}
