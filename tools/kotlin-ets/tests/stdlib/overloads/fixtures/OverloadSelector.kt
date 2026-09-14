package stdliboverloads

class OverloadItem(val value: Int)

class OverloadSelector(val trace: MutableList<Int>) {
    fun select(value: Int): Int {
        trace.add(300 + value)
        return choose(value, trace)
    }

    fun select(value: Double): Int {
        trace.add(400)
        return choose(value, trace)
    }

    fun accept(value: Int, keep: Boolean): Boolean {
        trace.add(500 + value)
        return keep
    }

    fun accept(value: Double, keep: Boolean): Boolean {
        trace.add(600)
        return keep
    }
}
