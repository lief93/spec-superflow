interface DefaultBody<T> { fun select(value: T): T = value }
class DefaultText : DefaultBody<String>
