open class PropertyBase(val value: Int)
class PropertyChild : PropertyBase(3)
fun inheritedProperty(value: PropertyChild): Int = value.value
