fun select(value: Int?): Int = 1
fun select(value: String?): Int = 2
fun ambiguous(): Int = select(null)
