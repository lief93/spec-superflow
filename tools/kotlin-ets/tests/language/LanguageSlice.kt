package languagefixture

class Counter(val base: Int, var total: Int = base) {
    fun add(amount: Int = 2): Int {
        total += amount
        return total
    }
}

fun calculate(first: Int, second: Int = 4, third: Int = 7): Int = first * 100 + second * 10 + third

fun languageSlice(): String {
    val counter = Counter(3)
    val mapped = calculate(third = counter.add(), first = counter.add(1))
    var sum = 0
    var index = 0
    while (index < 4) {
        index++
        if (index == 2) continue
        sum += index
    }
    val adjust: (Int) -> Int = { value -> value + sum }
    val choice = when (sum) {
        8 -> adjust(2)
        else -> 0
    }
    return "$mapped:${counter.total}:$sum:$choice"
}
