package iterationmodules

fun main() {
    println(transfer(4, 7))
    println(continuedCursor())
    println(nullableTransfer(null))
    println(nullableTransfer(9))
    println(rangeTransfer(Int.MIN_VALUE, Int.MAX_VALUE))
}
