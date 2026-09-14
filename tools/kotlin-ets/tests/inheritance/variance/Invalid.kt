interface InvalidOut<out T> { fun write(value: T) }
interface InvalidIn<in T> { fun read(): T }
interface InvalidMutable<out T> { var value: T }
