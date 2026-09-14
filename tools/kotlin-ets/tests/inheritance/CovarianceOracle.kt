fun main() {
    val factory: ResultFactory = NarrowFactory()
    println(factory.create() is NarrowResult)
    println(NarrowFactory().create() is NarrowResult)
    println(SecondaryChild().value)
}
