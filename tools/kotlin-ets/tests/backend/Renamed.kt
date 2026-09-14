package renamedfixture

object Bias {
    val amount: Int = 5
    fun shift(value: Int, extra: Int = 3): Int = value + amount + extra
}

fun assemble(first: Int, second: Int = 6, third: Int = 9): Int = first * 100 + second * 10 + third

fun evaluate(limit: Int): Int {
    var sum = 0
    var index = 0
    while (index < limit) {
        index++
        if (index == 2) continue
        sum += index
    }
    val transform: (Int) -> Int = { value -> value + sum }
    val selected = if (sum > 2) transform(2) else transform(1)
    return assemble(third = Bias.shift(selected), first = transform(3))
}

fun ruleValue(value: Int): Int = value
fun ruleEntry(value: Int): Int = ruleValue(value)
