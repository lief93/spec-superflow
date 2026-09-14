package ui.test

import sample.buttonLabel
import sample.pageModel

fun main() {
    for (page in listOf(0, 1, 2, 3, 2)) {
        val model = pageModel(page)
        println("$page:${model.title}:${model.detail}:${buttonLabel(page)}")
    }
}
