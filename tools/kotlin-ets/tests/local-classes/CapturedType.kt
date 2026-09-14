package classboundaries

fun <T> capturedType(value: T): T {
    class CapturedType(val item: T)
    return CapturedType(value).item
}
