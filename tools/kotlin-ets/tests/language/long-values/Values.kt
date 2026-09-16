package longvalues

class Contact(val id: Long)
fun identity(value: Long): Long = Contact(value).id
fun observations(): List<String> = listOf(
    "${identity(0L)}", "${identity(9007199254740993L)}",
    "${identity(Long.MAX_VALUE)}", "${identity(Long.MIN_VALUE)}",
    "${identity(-1L)}", "${-identity(Long.MIN_VALUE)}"
)
