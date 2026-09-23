package projectconsumer

import projectdependency.injected

fun overloadedState(): StateHolder = injected("key")
