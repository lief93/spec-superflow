package declarationvariance

fun <T> getCell(cell: Cell<T>): T = cell.value
fun readGeneric(cell: Cell<out Value>): Int = getCell(cell).number
fun projectedGeneric(seed: Int): Int = readGeneric(Cell(Specific(seed)))

class Channel<T>(var value: T) {
    fun <R> visit(visitor: (T) -> R): R = visitor(value)
    fun replace(factory: () -> T) { value = factory() }
    fun later(): () -> T = { value }
}

fun readChannel(channel: Channel<out Value>): Int = channel.visit { it.number }
fun replaceChannel(channel: Channel<in Specific>, seed: Int) { channel.replace { Specific(seed) } }
fun laterChannel(channel: Channel<out Value>): Int = channel.later()().number
fun projectedVisit(seed: Int): Int = readChannel(Channel(Specific(seed)))
fun projectedReplace(seed: Int): Int {
    val channel = Channel<Value>(Value(0))
    replaceChannel(channel, seed)
    return channel.value.number
}
fun projectedLater(seed: Int): Int = laterChannel(Channel(Specific(seed)))
