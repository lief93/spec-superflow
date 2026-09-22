package colorscheme

fun main() {
    roles(scheme(false)).forEach { println(it) }
    roles(scheme(true)).forEach { println(it) }
    overrides().forEach { println(it) }
    callForms().forEach { println(it) }
}
