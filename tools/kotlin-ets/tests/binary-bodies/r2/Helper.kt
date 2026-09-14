package genericbinary

inline fun <Leaf : Any, Output : Any> helper(value: Leaf, action: (Leaf) -> Output): Output = action(value)
