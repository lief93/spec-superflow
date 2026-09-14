package genericmethods

interface MethodProjector<C> {
    fun <R> project(value: C, transform: (C) -> R): R
}

class MethodItem(val value: Int)
