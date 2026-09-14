package classboundaries

open class CaptureBase

fun capturedBase(seed: Int): Int {
    class Child : CaptureBase() {
        fun read(): Int = seed
    }
    return Child().read()
}
