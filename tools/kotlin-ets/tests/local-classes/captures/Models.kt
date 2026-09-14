package capturefixture

class Model(var value: Int)

class Trace {
    var log: String = ""
    fun mark(label: String, value: Int): Int {
        log += label
        return value
    }
}
