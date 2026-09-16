package uiinit

var order = 0
var showOther = false
var showFailure = false
fun mark(value: Int): Int {
    order = order * 10 + value
    return value
}
