class Projected<C> { fun <T> select(value: T): T = value }
fun projected(value: Projected<*>): Int = value.select(1)
