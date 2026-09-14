fun local(value: Int): Int {
    class Local(val extra: Int) { constructor() : this(value) }
    return Local().extra
}
