package stdlibcases

fun wideMath(a: Long, b: Long): Long = a + b
fun localeCase(s: String): String = s.lowercase()
fun ignoredCase(s: String, part: String): Boolean = s.contains(part, ignoreCase = true)
fun charAt(s: String, index: Int): Char = s[index]
fun insert(values: MutableList<Int>, index: Int, value: Int) = values.add(index, value)
fun sequenceMap(values: Sequence<Int>): Sequence<Int> = values.map { it + 1 }
