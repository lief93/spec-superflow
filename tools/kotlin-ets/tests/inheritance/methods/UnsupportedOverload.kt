class Overloads {
    fun <T> select(value: T): T = value
    fun <T> select(value: T, flag: Boolean): T = value
}
