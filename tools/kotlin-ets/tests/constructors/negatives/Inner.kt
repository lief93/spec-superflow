class Outer(val value: Int) {
    inner class Inner(val extra: Int) { constructor() : this(value) }
}
