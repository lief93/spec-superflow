package projectdependency

fun <T : Any> injected(): T = error("source dependency only")
fun <T : Any> injected(key: String): T = error(key)
fun <T : Any> constructed(): T = error("source dependency only")
