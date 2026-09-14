package localclasses

class Envelope {
    class Node(val value: Int) {
        fun read(): Int = value + 1
    }
}

private class PrivateEnvelope {
    class Hidden(val value: Int)
}

fun local(seed: Int): Int {
    class Local(val value: Int) {
        fun read(): Int = value - 2
    }
    return Local(seed).read()
}
