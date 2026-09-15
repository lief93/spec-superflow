open class FloatBody {
    open fun choose(value: Int): Int = value
    open fun choose(value: Double): Double = value + 0.5
}

fun floatBody(seed: Int): Double = FloatBody().choose(seed.toDouble()) + FloatBody().choose(seed)
