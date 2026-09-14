fun sequenceValues(values: Sequence<Int>): Int {
    var result = 0
    for (value in values) result += value
    return result
}
