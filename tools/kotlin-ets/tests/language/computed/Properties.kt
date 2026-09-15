package computed

var base: Int = 0
var reads: Int = 0
var writes: Int = 0

var score: Int
    get() { reads++; return base * 2 }
    set(adjusted) { writes++; base = if (adjusted < 0) 0 else adjusted / 2 }

val optional: String?
    get() = if (base == 0) null else "V" + base

private val hidden: Int
    get() = base + 100

fun reset(value: Int) { base = value; reads = 0; writes = 0 }
fun snapshot(): String = "$base:$reads:$writes:${optional ?: "-"}:$hidden"
