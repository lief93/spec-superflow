package doublerelations

fun leftOperand(value: Double, trace: MutableList<Int>): Double { trace.add(1); return value }
fun rightOperand(value: Double, trace: MutableList<Int>): Double { trace.add(2); return value }

fun less(left: Double, right: Double, trace: MutableList<Int>): Boolean =
    leftOperand(left, trace) < rightOperand(right, trace)
fun lessEqual(left: Double, right: Double, trace: MutableList<Int>): Boolean =
    leftOperand(left, trace) <= rightOperand(right, trace)
fun greater(left: Double, right: Double, trace: MutableList<Int>): Boolean =
    leftOperand(left, trace) > rightOperand(right, trace)
fun greaterEqual(left: Double, right: Double, trace: MutableList<Int>): Boolean =
    leftOperand(left, trace) >= rightOperand(right, trace)
