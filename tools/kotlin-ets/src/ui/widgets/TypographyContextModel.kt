package dev.ets.widgets

/** A typography scope merges a provided style into its inherited style. */
data class TypographyContext<V, S>(val inheritedStyle: V, val providedStyle: V, val source: S)

/** Content executes with the typography context at its invocation site. */
data class TypographySlot<V, C, S>(val context: TypographyContext<V, S>, val content: C, val source: S)
