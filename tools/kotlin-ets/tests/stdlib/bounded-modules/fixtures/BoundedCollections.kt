package boundedmodules

fun <R, T : BoundedReadable<R>> readValues(values: List<T>): List<R> = values.map { it.read() }
fun <T : BoundedReadable<Int>> retainPositive(values: List<T>): List<T> = values.filter { it.read() > 0 }
fun <T : BoundedReadable<Int>> rejectPositive(values: List<T>): List<T> = values.filterNot { it.read() > 0 }
fun <T : BoundedBase> readClasses(values: List<T>): List<Int> = values.map { it.read() }
fun <T : BoundedBase> retainClasses(values: List<T>): List<T> = values.filter { it.read() > 0 }
