package boundedmodules

interface BoundedReadable<R> { fun read(): R }

class BoundedNumber(val value: Int, val trace: MutableList<Int>) : BoundedReadable<Int> {
    override fun read(): Int { trace.add(value); return value }
}

class BoundedText(val value: String) : BoundedReadable<String> {
    override fun read(): String = value
}

open class BoundedBase(val value: Int, val trace: MutableList<Int>) {
    open fun read(): Int { trace.add(value); return value }
}

class BoundedFailure(val value: Int, val trace: MutableList<Int>) : BoundedReadable<Int> {
    override fun read(): Int { trace.add(value); return 12 / (value - 2) }
}

class BoundedMutator(val value: Int, val trace: MutableList<Int>, val change: () -> Unit) : BoundedReadable<Int> {
    override fun read(): Int { trace.add(value); change(); return value }
}

class BoundedAction(val action: () -> Int) : BoundedReadable<Int> {
    override fun read(): Int = action()
}
