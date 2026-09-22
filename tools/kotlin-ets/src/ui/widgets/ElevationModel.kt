package dev.ets.widgets

/** Platform-neutral Material card elevation states retained until a target consumer chooses a legal effect. */
data class CardElevation<V, S>(val default: V, val pressed: V, val focused: V,
    val hovered: V, val dragged: V, val disabled: V, val source: S)
