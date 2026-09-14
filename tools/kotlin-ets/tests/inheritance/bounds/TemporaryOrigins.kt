package temporaryorigins

class ProbeBox(val value: Int)
inline fun ProbeBox.twice(): Int = value + value

// Language/typed-tree seam only: the public source guard still reserves __ets names.
fun temporaryNames(__etsTmp0: Int): Int {
    return ProbeBox(__etsTmp0).twice() + ProbeBox(__etsTmp0).twice()
}

class StrictFields(var arguments: Int, var eval: Int)
class StrictMethods {
    fun arguments(): Int = 3
    fun eval(): Int = 4
}
class TypeNames<eval, arguments>

fun strictValues(eval: Int, arguments: Int): Int {
    val eval_0 = 4
    val arguments_2 = 5
    return eval + eval + arguments + arguments + eval_0 + arguments_2
}
