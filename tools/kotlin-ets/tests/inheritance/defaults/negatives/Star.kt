interface StarDefaults<T> { fun pick(value: T? = null): T? }
fun starDefault(value: StarDefaults<*>): Any? = value.pick()
