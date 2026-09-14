package declarationvariance

fun widen(value: Producer<Specific>): Producer<Value> = value
fun narrow(value: Consumer<Value>): Consumer<Specific> = value
fun <T : Producer<Value>> bounded(value: T): Int = value.read().number
fun covariance(seed: Int): Int = bounded(widen(Box(Specific(seed))))
fun contravariance(seed: Int): Int = narrow(ValueConsumer()).accept(Specific(seed))
fun nested(seed: Int): Int {
    val inner: Producer<Specific> = Box(Specific(seed))
    val outer: Producer<Producer<Specific>> = Box(inner)
    val widened: Producer<Producer<Value>> = outer
    return widened.read().read().number
}
fun property(seed: Int): Int {
    val narrow: View<Specific> = StoredView(Specific(seed))
    val wide: View<Value> = narrow
    return wide.value.number
}
fun mixed(seed: Int): Int {
    val original: Transform<Value, Specific> = IdentityTransform()
    val converted: Transform<Specific, Value> = original
    return converted.apply(Specific(seed)).number
}
fun nullable(seed: Int): Int {
    val narrow: Producer<Specific> = Box(Specific(seed))
    val wide: Producer<Value?> = narrow
    return wide.read()?.number ?: -1
}
