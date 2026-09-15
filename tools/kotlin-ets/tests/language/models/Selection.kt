package models

var selected: Card? = null

fun choose(card: Card?) { selected = card }
fun selectedLabel(): String = selected?.display() ?: "None"
fun selectedCount(fallback: Int = 0): Int = selected?.count ?: fallback
fun adjustSelection(extra: Int) { selected = selected?.adjusted(extra) }
