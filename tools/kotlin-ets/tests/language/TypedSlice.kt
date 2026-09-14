package languagefixture

fun identity(seed: Int): Int {
    val held = seed
    return held
}

fun adapted(seed: Int): Int = seed + 1
fun defaults(first: Int, second: Int = 4): Int = first
fun omitted(): Int = defaults(3)
fun effectOnly() { java.time.Instant.now() }
fun directEffect() { java.lang.System.gc() }
fun coercedEffect(): () -> Unit = { java.time.Instant.now() }
fun storedEffect() { val instant = java.time.Instant.now() }
fun returnedEffect(): java.time.Instant = java.time.Instant.now()
fun acrossFile(): Int = helper(5)
object TypedObject
fun singletonReference(): TypedObject = TypedObject
