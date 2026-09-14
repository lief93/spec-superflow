package defaultbinary

inline fun <Leaf : Any> Leaf.defaultHelper(mark: () -> Unit): Leaf {
    mark()
    return this
}
