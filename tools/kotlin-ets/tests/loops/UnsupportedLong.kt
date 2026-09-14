fun longIteration(first: Long, last: Long): Long {
    var result = 0L
    for (value in first..last) result += value
    return result
}
