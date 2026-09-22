package dev.ets.widgets

/** Platform-neutral static corner semantics retained until a target consumer chooses a legal API. */
enum class CornerShapeKind { ROUNDED, CUT, CIRCLE }

data class CornerShape<V, S>(val kind: CornerShapeKind, val topStart: V, val topEnd: V,
    val bottomEnd: V, val bottomStart: V, val source: S)

data class ThemeShapes<V, S>(val extraSmall: CornerShape<V, S>, val small: CornerShape<V, S>,
    val medium: CornerShape<V, S>, val large: CornerShape<V, S>,
    val extraLarge: CornerShape<V, S>, val source: S)
