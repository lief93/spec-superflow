package chainnegative.localowner
fun local(seed: Int): Int {
    class Outer(val value: Int) {
        inner class Inner { inner class Deep { fun read(): Int = value } }
    }
    return Outer(seed).Inner().Deep().read()
}
