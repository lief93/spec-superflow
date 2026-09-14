package genericmethods

class MethodPipeline<C>(val projector: MethodProjector<C>) {
    fun <R> mapped(values: List<C>, transform: (C) -> R, predicate: (R) -> Boolean): Iterator<R> =
        values.map { projector.project<R>(it, transform) }.filter(predicate).iterator()

    fun selected(values: List<C>, predicate: (C) -> Boolean, negate: Boolean): List<C> =
        if (negate) values.filterNot { projector.project<Boolean>(it, predicate) }
        else values.filter { projector.project<Boolean>(it, predicate) }

    fun cursor(values: List<C>): Iterator<C> = values.iterator()
}
