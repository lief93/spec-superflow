package virtualoverloads

class Child : Base<String>(), TextSelector {
    override fun choose(value: String): String = "child:$value"
    override fun choose(value: Int, extra: Int): Int = value - extra
    override fun choose(value: Double): String = "child-double"
    fun choose(value: Boolean): String = if (value) "yes" else "no"
}

class Generic<U> : Base<U>() {
    override fun choose(value: U): U = value
    override fun choose(value: Int, extra: Int): Int = value * extra
    override fun <W> selectItem(value: W): W = value
    override fun selectItem(value: Int, extra: Int): Int = value - extra
}

class Retained : Base<String>()

fun inherited(seed: Int): String {
    val value = Retained()
    return "${value.choose("x")}:${value.choose(seed, 3)}:${value.choose_0(seed)}"
}

class DefaultChild(seed: Int) : Defaults(seed) {
    override fun label(value: Int): String = "child:$value"
    override fun label(value: String): String = "child-text:$value"
}

class NumericChild : Numeric() {
    override fun choose(value: Int): Int = value - 1
    override fun choose(value: Double): Int = 29
}

fun numeric(seed: Int): String {
    val value: Numeric = NumericChild()
    return "${value.choose(seed)}:${value.choose(2.0)}"
}

fun dispatch(seed: Int): String {
    val child = Child()
    val base: Base<String> = child
    val selector: Selector<String> = child
    val text: TextSelector = child
    return "${base.choose("a")}:${selector.choose("b")}:${text.choose("c")}:" +
        "${base.choose(seed, 2)}:${selector.choose(seed, 3)}:${child.choose(true)}:${base.choose(2.0)}"
}

fun generic(seed: Int): String {
    val child = Generic<Int>()
    val base: Base<Int> = child
    val selector: Selector<Int> = child
    return "${base.choose(seed)}:${selector.choose(seed, 3)}:${child.choose(1.0)}:${child.unchanged(seed)}:" +
        "${child.selectItem("x")}:${base.selectItem(seed, 5)}"
}

fun defaults(seed: Int): String {
    val value: Defaults = DefaultChild(seed)
    return "${value.label()}:${value.label(seed + 1)}:${value.label("a")}:${Unrelated().choose(seed)}"
}

fun effects(seed: Int): String {
    var count = seed
    val select = { count += 1; Child() }
    val next = { count += 2; count }
    val answer = select().choose(next(), next())
    return "$answer:$count"
}
