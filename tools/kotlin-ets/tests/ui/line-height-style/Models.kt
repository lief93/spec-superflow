package lineheightstyle

import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp

fun alignmentCode(value: LineHeightStyle.Alignment): Int = when (value) {
    LineHeightStyle.Alignment.Top -> 1
    LineHeightStyle.Alignment.Center -> 2
    LineHeightStyle.Alignment.Proportional -> 3
    LineHeightStyle.Alignment.Bottom -> 4
    else -> 0
}

fun trimCode(value: LineHeightStyle.Trim): Int = when (value) {
    LineHeightStyle.Trim.FirstLineTop -> 1
    LineHeightStyle.Trim.LastLineBottom -> 2
    LineHeightStyle.Trim.Both -> 3
    LineHeightStyle.Trim.None -> 4
    else -> 0
}

fun modeCode(value: LineHeightStyle.Mode): Int = when (value) {
    LineHeightStyle.Mode.Fixed -> 1
    LineHeightStyle.Mode.Minimum -> 2
    else -> 0
}

fun styleCode(value: LineHeightStyle): Int =
    alignmentCode(value.alignment) * 100 + trimCode(value.trim) * 10 + modeCode(value.mode)

fun makeStyle(
    alignment: LineHeightStyle.Alignment,
    trim: LineHeightStyle.Trim,
    mode: LineHeightStyle.Mode,
): LineHeightStyle = LineHeightStyle(alignment, trim, mode)

fun makeLegacyStyle(
    alignment: LineHeightStyle.Alignment,
    trim: LineHeightStyle.Trim,
): LineHeightStyle = LineHeightStyle(alignment, trim)

fun copied(value: LineHeightStyle): LineHeightStyle =
    value.copy(trim = LineHeightStyle.Trim.None)

fun styled(value: LineHeightStyle): TextStyle =
    TextStyle(lineHeight = 24.sp, lineHeightStyle = value)

fun copiedStyle(value: TextStyle): TextStyle =
    value.copy(fontSize = 18.sp)

fun replacedStyle(value: TextStyle): TextStyle =
    value.copy(lineHeightStyle = LineHeightStyle.Default)

fun textStyleValue(value: TextStyle): LineHeightStyle? = value.lineHeightStyle

fun semanticSnapshot(): List<Int> {
    val top = LineHeightStyle.Alignment.Top
    val center = LineHeightStyle.Alignment.Center
    val proportional = LineHeightStyle.Alignment.Proportional
    val bottom = LineHeightStyle.Alignment.Bottom
    val first = LineHeightStyle.Trim.FirstLineTop
    val last = LineHeightStyle.Trim.LastLineBottom
    val both = LineHeightStyle.Trim.Both
    val none = LineHeightStyle.Trim.None
    val fixed = LineHeightStyle.Mode.Fixed
    val minimum = LineHeightStyle.Mode.Minimum
    val explicit = makeStyle(center, none, fixed)
    val legacy = makeLegacyStyle(bottom, last)
    val changed = copied(legacy)
    val textStyle = copiedStyle(styled(explicit))
    val replaced = replacedStyle(textStyle)
    return listOf(
        alignmentCode(top), alignmentCode(center), alignmentCode(proportional), alignmentCode(bottom),
        trimCode(first), trimCode(last), trimCode(both), trimCode(none),
        modeCode(fixed), modeCode(minimum),
        styleCode(LineHeightStyle.Default), styleCode(explicit), styleCode(legacy), styleCode(changed),
        if (explicit == makeStyle(center, none, fixed)) 1 else 0,
        if (explicit == legacy) 1 else 0,
        styleCode(textStyleValue(textStyle)!!),
        styleCode(textStyleValue(replaced)!!),
        if (TextStyle().lineHeightStyle == null) 1 else 0,
    )
}
