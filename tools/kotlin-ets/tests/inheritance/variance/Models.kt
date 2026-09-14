package declarationvariance

open class Value(val number: Int)
class Specific(number: Int) : Value(number)
interface Producer<out T> { fun read(): T }
interface Consumer<in T> { fun accept(value: T): Int }
class Box<out T>(private val stored: T) : Producer<T> {
    override fun read(): T = stored
}
class ValueConsumer : Consumer<Value> {
    override fun accept(value: Value): Int = value.number
}
interface View<out T> { val value: T }
class StoredView<out T>(override val value: T) : View<T>
interface Transform<in A, out B> { fun apply(value: A): B }
class IdentityTransform : Transform<Value, Specific> {
    override fun apply(value: Value): Specific = Specific(value.number)
}
