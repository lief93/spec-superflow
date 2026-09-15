package models

data class Card(val title: String, val count: Int = 1, val subtitle: String? = null) {
    fun adjusted(extra: Int): Card = copy(count = count + extra)
    fun display(): String = subtitle?.let { title + ":" + it } ?: title
}
