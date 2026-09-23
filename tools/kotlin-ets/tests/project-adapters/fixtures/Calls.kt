package projectconsumer

import projectdependency.constructed
import projectdependency.injected

fun injectedState(): StateHolder = injected()
fun injectedBox(): Box<StateHolder> = injected()
fun constructedState(): ConstructedHolder = constructed()
fun bodyFirst(): StateHolder = localState()
