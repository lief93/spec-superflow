package initialization

fun before(): String = trace()
fun methodFirst(): String = "${untouched()}:${snapshot()}:${trace()}"
fun propertyFirst(): String = "$first:${snapshot()}:${trace()}"
fun writeFirst(value: Int): String { score = value; return "${snapshot()}:${trace()}" }
fun readFailure(): Int = crash
fun readOuterFailure(): Int = outer
fun defaultFirst(): String = "${withDefault()}:${snapshot()}:${trace()}"
fun legacyInitializer(): String = "${initialized.initialPage}:${initialized.calls}:${initialized.next()}"
