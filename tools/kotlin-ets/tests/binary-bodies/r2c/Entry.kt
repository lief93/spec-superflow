package defaultbinary

inline fun <Value : Any> Value.defaultSelect(
    noinline mark: () -> Unit,
    selected: Value = this.defaultHelper(mark),
): Value = selected
