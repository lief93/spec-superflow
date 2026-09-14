class LocalInitializer {
    val value: Int = run {
        class Local(val value: Int)
        Local(7).value
    }
    constructor(number: Int)
    constructor(text: String)
}
