package nonlocal

fun early(value: String?): String {
    value?.let { return it }
    return "None"
}
