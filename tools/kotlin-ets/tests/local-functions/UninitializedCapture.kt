package localfixture

fun uninitializedCapture(): String {
    lateinit var value: String
    fun initialize() {
        value = "ready"
    }
    initialize()
    return value
}
