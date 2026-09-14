open class PropertyParent { open val value: Int = 1 }
class PropertyOverride : PropertyParent() { override val value: Int = 2 }
