open class PropertyBase<T>(val value: T)
class PropertyChild : PropertyBase<Int>(1)
fun inheritedProperty(child: PropertyChild): Int = child.value
