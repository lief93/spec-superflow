package enums

enum class Stage(val code: Int) {
    FIRST(mark(4)), SECOND(mark(8)), LAST(mark(12));
    fun label(prefix: String = "go:"): String = "$prefix$name:$code"
}

enum class Broken(val code: Int) { ENTRY(1 / 0) }
