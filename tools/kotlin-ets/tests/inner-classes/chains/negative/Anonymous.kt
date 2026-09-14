package chainnegative.anonymous
class Outer {
    inner class Inner {
        inner class Deep { fun anonymous(): Any = object { val parent = this@Inner } }
    }
}
