interface Ancestor<T> { fun read(): T }
interface Left : Ancestor<Int>
interface Right : Ancestor<String>
abstract class Conflicting : Left, Right
