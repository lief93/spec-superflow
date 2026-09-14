package nestedfixture

class Node(var value: Int) {
    fun read(): Int = value
}

class Box<T>(val value: T) {
    fun read(): T = value
}

class Outer<T>(val value: T) {
    class Node(var value: Int) {
        fun read(): Int = value + 10
    }
    class Cell<T>(val value: T) {
        fun read(): T = value
    }
}

class Other {
    class Node(var value: Int) {
        fun read(): Int = value + 20
    }
    class Cell<T>(val value: T) {
        fun read(): T = value
    }
}

interface Cell<T> {
    fun read(): T
}

fun Node_0(value: Int): Int = value + 30
fun Local_0(value: Int): Int = value + 40
