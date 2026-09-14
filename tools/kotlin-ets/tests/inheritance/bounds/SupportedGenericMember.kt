interface Reader { fun <A> read(value: A): A }
fun <T : Reader> genericMember(value: T): Int = value.read(1)
