package dev.ets.widgets

/** Static compiler semantics, not a widget/recomposition runtime.
 * Values and locations belong to the caller; this module knows no source or target platform.
 * Modifier lists run outermost first and retain duplicates. Slots retain child order.
 */
sealed interface Widget<V, S> {
    val modifiers: List<WidgetModifier<V, S>>
    val source: S

    data class Text<V, S>(val text: WidgetValue<V, S>, val style: WidgetTextStyle<V, S>,
        override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Image<V, S>(val image: ImageSource<V, S>, val contentDescription: V,
        override val modifiers: List<WidgetModifier<V, S>>, override val source: S) : Widget<V, S>
    data class Button<V, S>(val onClick: V, val enabled: V?, val content: Children<V, S>,
        override val modifiers: List<WidgetModifier<V, S>>, override val source: S) : Widget<V, S>
    data class TextField<V, S>(val value: V, val onValueChange: V, val enabled: V?,
        override val modifiers: List<WidgetModifier<V, S>>, override val source: S) : Widget<V, S>
    data class Row<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Column<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
    data class Box<V, S>(val children: Children<V, S>, override val modifiers: List<WidgetModifier<V, S>>,
        override val source: S) : Widget<V, S>
}

/** Semantic value type and source origin are explicit at the platform seam. */
enum class WidgetValueType { STRING, COLOR, FONT_SIZE, FONT_WEIGHT, FONT_FAMILY, LINE_HEIGHT }

sealed interface WidgetValueProvenance {
    data object Literal : WidgetValueProvenance
    data class Resource(val reference: String) : WidgetValueProvenance
    data class ThemeToken(val reference: String) : WidgetValueProvenance
    data class Expression(val reference: String?) : WidgetValueProvenance
}

data class WidgetValue<V, S>(val type: WidgetValueType, val value: V,
    val provenance: WidgetValueProvenance, val source: S)

data class WidgetTextStyle<V, S>(val fontSize: WidgetValue<V, S>?,
    val fontWeight: WidgetValue<V, S>?, val fontFamily: WidgetValue<V, S>?,
    val lineHeight: WidgetValue<V, S>?)

data class Children<V, S>(val widgets: List<Widget<V, S>>)

/** The source kind survives the platform seam; no resource or URL is reduced to source text. */
sealed interface ImageSource<V, S> {
    val value: V
    val source: S
    data class Resource<V, S>(override val value: V, override val source: S) : ImageSource<V, S>
    data class Url<V, S>(override val value: V, override val source: S) : ImageSource<V, S>
}

sealed interface WidgetModifier<V, S> {
    val source: S
    data class Size<V, S>(val width: V, val height: V,
        override val source: S) : WidgetModifier<V, S>
    data class Width<V, S>(val value: V, override val source: S) : WidgetModifier<V, S>
    data class Height<V, S>(val value: V, override val source: S) : WidgetModifier<V, S>
    data class Padding<V, S>(val start: V, val top: V, val end: V, val bottom: V,
        override val source: S) : WidgetModifier<V, S>
    data class Background<V, S>(val color: WidgetValue<V, S>, override val source: S) : WidgetModifier<V, S>
    data class Click<V, S>(val onClick: V, val enabled: V?,
        override val source: S) : WidgetModifier<V, S>
}
