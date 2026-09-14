package genericmethods

open class MethodBase<C>(val trace: MutableList<Int>) : MethodProjector<C> {
    override fun <B> project(value: C, transform: (C) -> B): B {
        trace.add(10)
        return transform(value)
    }
}

class MethodDerived<C>(val events: MutableList<Int>) : MethodBase<C>(events) {
    override fun <D> project(value: C, transform: (C) -> D): D {
        events.add(20)
        return transform(value)
    }
}
