package modulefixture

fun describe(value: Int): String = label(bump(Counter(value)).value)

private fun localOffset(value: Int): Int = value + 2
fun entryLocalValue(value: Int): Int = localOffset(value)

fun privateClassValue(value: Int): Int = hiddenClassValue(value)

fun crossFileInlineValue(value: Int): Int = inlineLocalValue(value)
fun crossFileInlineGeneric(value: Int): String = "${inlineIdentity(value)}/${inlineIdentity("text")}"
fun crossFileInlineDefault(value: Int): Int = inlineDefault(value)
fun crossFileInlineOverloaded(value: Int): Int = inlineOverloaded(value)
