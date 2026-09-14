package shadowfixture

class Outer {
    class Node(val value: Int)
    class Safe(val value: Int)
    class Unique(val value: Int)
}

class Another {
    class Node(val value: Int)
}

class Holder(Node: Int) {
    val value = Outer.Node(Node).value
}

fun Node_0(value: Int): Int = value + 100
