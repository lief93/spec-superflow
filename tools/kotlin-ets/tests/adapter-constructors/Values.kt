package constructorvalues

import constructorapi.Amount

var reads = 0
fun next(): Double { reads += 1; return 2.5 }
class Source(val value: Double)
fun create(value: Double): Amount = Amount(value)
fun read(value: Amount): Double = value.value
fun observations(): List<Double> {
    val amount = create(next())
    Amount(next())
    val source = Source(read(amount))
    return listOf(source.value, reads.toDouble())
}
