package filterrejected
fun nonLocal(values: List<Int>): Int {
    values.filter { return 1 }
    return 2
}
