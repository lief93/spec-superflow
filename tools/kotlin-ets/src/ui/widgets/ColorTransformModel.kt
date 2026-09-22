package dev.ets.widgets

/** Platform-neutral channel replacement; null channels retain the input color component. */
data class ColorTransform<V, S>(val input: V, val alpha: V?, val red: V?, val green: V?, val blue: V?,
    val source: S)
