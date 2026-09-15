package declarationcomposition

open class Value(val number: Int)
class Specific(number: Int) : Value(number)
class Cell<T>(var value: T)
fun <T> read(cell: Cell<T>): T = cell.value

inline fun copied(cell: Cell<out Value>): Int = read(cell).number
fun inlineCapture(seed: Int): Int = copied(Cell(Specific(seed)))

fun localCapture(seed: Int): Int {
    val cell: Cell<out Value> = Cell(Specific(seed))
    fun local(): Int = read(cell).number
    return local()
}

inline fun <T : Value> genericCopy(cell: Cell<out T>): Int = read(cell).number
fun substitutedCapture(seed: Int): Int = genericCopy(Cell(Specific(seed)))

inline fun <T : Value> nestedCopy(cell: Cell<out T>): Int = genericCopy(cell)
fun nestedCapture(seed: Int): Int = nestedCopy(Cell(Specific(seed)))

inline fun <T : Value> copiedInput(cell: Cell<in T>): Boolean = read(cell) == null
fun inputCapture(seed: Int): Boolean = copiedInput<Specific>(Cell<Any?>(if (seed == 0) null else Specific(seed)))

class Bounded<T : Value>(val value: T)
fun <T : Value> boundedRead(cell: Bounded<T>): T = cell.value
fun finiteBound(cell: Bounded<out Value>): Int = boundedRead(cell).number
fun boundCapture(seed: Int): Int = finiteBound(Bounded(Specific(seed)))
