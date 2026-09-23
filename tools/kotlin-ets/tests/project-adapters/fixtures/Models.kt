package projectconsumer

class StateHolder(val label: String)
class ConstructedHolder(val label: String)
class Box<T>(val value: T)
class MissingHolder(val label: String)
class WrongHolder(val label: String)
class VoidHolder(val label: String)
class ArgumentHolder(val label: String)
class ScopeHolder(val label: String)

fun localState(): StateHolder = StateHolder("body")
