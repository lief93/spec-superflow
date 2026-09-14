package reviewshadow

class Outer {
    class Node(val value: Int)
}
fun result(Node: Int): Int = Outer.Node(Node).value
