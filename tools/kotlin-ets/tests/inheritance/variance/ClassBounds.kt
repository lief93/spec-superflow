package declarationvariance

open class ReadingBase<T>(private val stored: T) {
    fun read(): T = stored
}
class LabelledReading(value: Specific) : ReadingBase<Specific>(value), Named {
    override val name: String = "reading"
}
fun <U, T> readNamed(value: T): U where T : ReadingBase<U>, T : Named = value.read()
fun <T> nameReading(value: T): String where T : Named, T : ReadingBase<Specific> = value.name
fun <T> asBase(value: T): ReadingBase<Specific> where T : ReadingBase<Specific>, T : Named = value
class ReadingHolder<U, T>(val value: T) where T : ReadingBase<U>, T : Named {
    fun label(): String = value.name
    fun read(): U = value.read()
}
fun classInterface(seed: Int): Int = readNamed<Specific, LabelledReading>(LabelledReading(Specific(seed))).number
fun interfaceClass(seed: Int): String = nameReading(LabelledReading(Specific(seed)))
fun classInterfaceReturn(seed: Int): Int = asBase(LabelledReading(Specific(seed))).read().number
fun classInterfaceHolder(seed: Int): String {
    val holder = ReadingHolder<Specific, LabelledReading>(LabelledReading(Specific(seed)))
    return holder.label() + ":" + holder.read().number
}

interface ReadingOps {
    var prefix: Int
    fun transform(value: Int): Int
}
class StatefulReading(seed: Int) : ReadingBase<Int>(seed), ReadingOps {
    override var prefix: Int = seed
    override fun transform(value: Int): Int = value + prefix
}
fun <T> mutateReading(value: T, amount: Int): Int where T : ReadingBase<Int>, T : ReadingOps {
    value.prefix = amount
    return value.transform(value.read())
}
fun classInterfaceMutation(seed: Int): Int = mutateReading(StatefulReading(seed), 2)
