package modulefixture

internal class Counter(var value: Int)

private class LocalCounter(val value: Int)

internal fun hiddenClassValue(value: Int): Int = LocalCounter(value).value
