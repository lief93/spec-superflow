fun localDefault(seed: Int): Int {
    open class Local { open fun pick(value: Int = seed): Int = value }
    return Local().pick()
}
