package collector

// Collection must not invoke the selected compiler, even for unresolved source.
fun application() = intentionallyUnresolvedApplicationSymbol()
