package crossfileoverloads

class Token(var value: Int)

class Trace {
    var value: String = ""

    fun mark(label: String, input: Int): Int {
        value += label
        return input
    }

    fun markDouble(label: String, input: Double): Double {
        value += label
        return input
    }
}
