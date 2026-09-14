fun composedProgression(first: Int, last: Int, stride: Int): Int {
    var result = 0
    for (value in first until last step stride) result += value
    return result
}
