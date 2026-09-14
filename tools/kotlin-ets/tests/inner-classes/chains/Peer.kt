package innerchains

class Peer(var value: Int) {
    inner class Inner(var value: Int) {
        inner class Deep(val value: Int) {
            fun read(): Int = this@Peer.value + this@Inner.value + value
        }
    }
}
