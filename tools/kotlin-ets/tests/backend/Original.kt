package backendfixture

object Offset {
    val amount: Int = 3
    fun add(value: Int, extra: Int = 2): Int = value + amount + extra
}

fun combine(first: Int, second: Int = 4, third: Int = 7): Int = first * 100 + second * 10 + third

fun execute(limit: Int): Int {
    var sum = 0
    var index = 0
    while (index < limit) {
        index++
        if (index == 2) continue
        sum += index
    }
    val transform: (Int) -> Int = { value -> value + sum }
    val selected = if (sum > 2) transform(2) else transform(1)
    return combine(third = Offset.add(selected), first = transform(3))
}

fun ruleValue(value: Int): Int = value
fun ruleEntry(value: Int): Int = ruleValue(value)
