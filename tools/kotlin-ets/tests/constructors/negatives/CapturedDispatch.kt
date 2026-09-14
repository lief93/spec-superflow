fun capturedDispatch(seed: Int): Int {
    class Local {
        val value: Int
        constructor(value: Int) { this.value = value + seed }
        constructor(value: String) { this.value = value.length + seed }
        fun read(): Int = value + seed
    }
    return Local(1).read() + Local("abc").read()
}
