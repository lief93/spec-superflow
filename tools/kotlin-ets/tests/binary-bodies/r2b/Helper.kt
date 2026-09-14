package extensionbinary

inline fun <Leaf : Any, Output : Any> Leaf.extHelper(stamp: Int, action: (Leaf, Leaf, Int) -> Output): Output =
    action(this, this, stamp + 1)
