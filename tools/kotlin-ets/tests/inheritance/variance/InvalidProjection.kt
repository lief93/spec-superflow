package invalidprojection

open class Value
class Specific : Value()
class Cell<T>(var value: T)
fun writeOut(cell: Cell<out Value>, value: Value) { cell.value = value }
fun writeStar(cell: Cell<*>) { cell.value = null }
fun readIn(cell: Cell<in Specific>): Specific = cell.value
fun invariant(cell: Cell<out Value>): Cell<Value> = cell
