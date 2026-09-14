interface FirstDefault { fun pick(value: Int = 1): Int }
interface DefaultMarker
fun <T> multipleDefault(value: T): Int where T : FirstDefault, T : DefaultMarker = value.pick()
