package models

fun scenario(minimum: Int, extra: Int, pick: Boolean): String {
    val originals = listOf(Card("A", 0), Card("B", 2, "Detail"), Card("C", 4))
    val items = originals.filter { it.count >= minimum }.map { it.adjusted(extra) }
    var total = 0
    for (item in items) total += item.count
    choose(if (pick && items.isNotEmpty()) items[0] else null)
    return selectedLabel() + ":" + selectedCount(-1) + ":" + items.size + ":" + total + ":" + originals[1].count
}

fun afterAdjustment(extra: Int): String {
    adjustSelection(extra)
    return selectedLabel() + ":" + selectedCount()
}
