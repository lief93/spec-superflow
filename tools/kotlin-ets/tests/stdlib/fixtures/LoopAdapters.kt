package loopadaptercases

fun ascendingLast(first: Int, last: Int, stride: Int): Int {
    var result = 42
    for (value in first..last step stride) result = value
    return result
}

fun descendingLast(first: Int, last: Int, stride: Int): Int {
    var result = 42
    for (value in first downTo last step stride) result = value
    return result
}
