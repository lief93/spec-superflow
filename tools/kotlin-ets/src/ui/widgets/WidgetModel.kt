package dev.ets.widgets

/** Static compiler semantics, not a widget/recomposition runtime.
 * Values and locations belong to the caller; this module knows no source or target platform.
 * Modifier lists run outermost first and retain duplicates. Slots retain child order.
 */
sealed interface Widget<V, S> {
    val modifiers: List<WidgetModifier<V, S>>
    val source: S

    data class Text<V, S>(val text: V, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Button<V, S>(val onClick: V, val enabled: V?, val content: Children<V, S>,
        override val modifiers: List<WidgetModifier<V, S>>, override val source: S) : Widget<V, S>
    data class Row<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Column<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Box<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
}

data class Children<V, S>(val widgets: List<Widget<V, S>>)

sealed interface WidgetModifier<V, S> {
    val source: S
    data class Width<V, S>(val value: V, override val source: S) : WidgetModifier<V, S>
    data class Height<V, S>(val value: V, override val source: S) : WidgetModifier<V, S>
    data class Padding<V, S>(val start: V, val top: V, val end: V, val bottom: V,
        override val source: S) : WidgetModifier<V, S>
}
