package classboundaries

class Outer<T>(val value: T) {
    inner class Inner {
        fun read(): T = value
    }
}
