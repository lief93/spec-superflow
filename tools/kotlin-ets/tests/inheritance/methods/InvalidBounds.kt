interface Marker
interface Base { fun <T> select(value: T): T }
class Derived : Base { override fun <T : Marker> select(value: T): T = value }
