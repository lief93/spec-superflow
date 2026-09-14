package declarationvariance

class Cell<T>(var value: T)
fun readProjected(cell: Cell<out Value>): Int = cell.value.number
fun writeProjected(cell: Cell<in Specific>, value: Specific) { cell.value = value }
fun emptyProjected(cell: Cell<*>): Boolean = cell.value == null
fun project(cell: Cell<Specific>): Cell<out Value> = cell
fun projectedRead(seed: Int): Int = readProjected(Cell(Specific(seed)))
fun projectedWrite(seed: Int): Int {
    val cell = Cell<Value>(Value(0))
    writeProjected(cell, Specific(seed))
    return cell.value.number
}
fun projectedStar(seed: Int): Boolean = emptyProjected(Cell(if (seed == 0) null else Specific(seed)))

class BoundedCell<T : Value>(var value: T)
fun readBounded(cell: BoundedCell<in Specific>): Int = cell.value.number
fun projectedBound(seed: Int): Int = readBounded(BoundedCell(Value(seed)))
fun readNested(cell: Cell<Cell<out Value>>): Int = cell.value.value.number
fun projectedNested(seed: Int): Int = readNested(Cell(project(Cell(Specific(seed)))))
