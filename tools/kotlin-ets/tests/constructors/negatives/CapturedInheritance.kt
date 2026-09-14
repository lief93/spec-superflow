open class CaptureBase

fun capturedInheritance(seed: Int): Int {
    class Local : CaptureBase {
        val value: Int
        constructor(value: Int) : super() { this.value = value + seed }
        constructor(value: String) : super() { this.value = value.length + seed }
        fun read(): Int = value + seed
    }
    return Local(1).read() + Local("abc").read()
}
