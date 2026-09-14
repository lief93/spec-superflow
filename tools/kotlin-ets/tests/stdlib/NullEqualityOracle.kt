package nullequalitycases

private fun emit(expression: String, value: Any) = println("{\"expression\":\"$expression\",\"value\":$value}")
fun main() {
    for (value in listOf(null, -1, 0, 2)) {
        val arg = value?.toString() ?: "null"
        emit("nullEquality.missing($arg)", missing(value))
        emit("nullEquality.nullFirst($arg)", nullFirst(value))
        emit("nullEquality.present($arg)", present(value))
        emit("nullEquality.choose($arg, 7)", choose(value, 7))
        emit("nullEquality.missingObject($arg)", missingObject(value))
        val log = mutableListOf<Int>()
        val result = chooseLogged(value, log)
        println("{\"expression\":\"(() => { const log = []; const result = nullEquality.chooseLogged($arg, log); return [result, log]; })()\"," +
            "\"value\":[$result,${log.joinToString(",", "[", "]")}]}")
    }
    emit("nullEquality.safeLength(null)", safeLength(null))
    emit("nullEquality.safeLength('')", safeLength(""))
    emit("nullEquality.safeLength('abc')", safeLength("abc"))
    emit("nullEquality.missing('text')", missing("text"))
    emit("nullEquality.nullFirst('text')", nullFirst("text"))
    emit("nullEquality.present('text')", present("text"))
}
