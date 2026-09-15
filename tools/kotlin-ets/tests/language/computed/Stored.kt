package computed

var storedReads: Int = 0
var storedWrites: Int = 0

var amount: Int = 6
    get() { storedReads++; return field }
    set(newAmount) { storedWrites++; field = if (newAmount < 0) 0 else newAmount }

var getterOnly: Int = 5
    get() = field + 1

var setterOnly: Int = 1
    set(next) { field = next * 2 }

var privateAmount: Int = 4
    get() = field + 10
    private set(next) { field = next }

fun initialStored(): String = "$storedReads:$storedWrites:$amount:$getterOnly:$setterOnly:$privateAmount"

fun resetStored(value: Int) {
    storedReads = 0
    storedWrites = 0
    amount = value
    privateAmount = value
}

fun storedTrace(): String = "$storedReads:$storedWrites:$privateAmount"
