package classboundaries

class Outer(val value: Int) {
    inner class Inner {
        fun read(): Int = value
    }
}
