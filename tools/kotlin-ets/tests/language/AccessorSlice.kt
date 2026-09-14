package accessorfixture

class Reading(val base: Int) {
    var reads: Int = 0
    var writes: Int = 0
    var value: Int = base
        get() {
            reads += 1
            return field + 1
        }
        set(next) {
            writes += 1
            if (next < 0) return
            field = next * 2
        }
    val doubled: Int
        get() = value * 2
    var normalized: Int = base
        set(next) { field = if (next < 0) 0 else next }
    val initialWrites: Int = writes
}

class ReadingOwner(val reading: Reading) {
    var lookups: Int = 0
    fun current(): Reading {
        lookups += 1
        return reading
    }
}

object AccessorDefaults {
    val step: Int
        get() = 3
}

fun accessorSlice(start: Int, next: Int): String {
    val reading = Reading(start)
    val owner = ReadingOwner(reading)
    val first = reading.value
    owner.current().value = next
    val second = reading.doubled
    reading.normalized = next
    return "$first:$second:${reading.reads}:${reading.writes}:${reading.normalized}:${owner.lookups}:${reading.initialWrites}:${AccessorDefaults.step}"
}

fun accessorUpdate(start: Int, next: Int): String {
    val reading = Reading(start)
    val owner = ReadingOwner(reading)
    val previous = owner.current().value++
    owner.current().value += next
    return "$previous:${reading.value}:${reading.reads}:${reading.writes}:${owner.lookups}"
}
