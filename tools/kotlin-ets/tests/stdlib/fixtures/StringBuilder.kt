package buildervalues

fun grouped(input: String, width: Int, separator: Char): String {
    val result = StringBuilder()
    var count = 0
    for (char in input) {
        if (count > 0 && count % width == 0) result.append(separator)
        result.append(char)
        count++
    }
    return result.toString()
}

fun observations(): List<String> {
    val builder = StringBuilder("prefix")
    val alias = builder.append(':')
    val missing: String? = null
    alias.append(missing).append("!")
    return listOf(grouped("123456789", 4, '-'), grouped("", 2, ' '), builder.toString(), alias.toString())
}
