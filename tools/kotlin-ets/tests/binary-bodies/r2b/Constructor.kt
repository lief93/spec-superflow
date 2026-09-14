package extensionbinary

class Artifact(val value: Int)

inline fun <Value : Any> Value.unsupported() {
    Artifact(1)
}
