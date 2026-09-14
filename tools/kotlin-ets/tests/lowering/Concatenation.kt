package loweringfixture

class Journal(val seed: Int) {
    var value: Int = seed
    var events: String = ""

    fun record(label: String): String {
        value += 1
        events += label
        return "$label$value"
    }
}

fun orderedConcatenation(initialValue: Int): String {
    val journal = Journal(initialValue)
    val prefix: String? = null
    val result = prefix + journal.record("A") + ("|" + journal.record("B"))
    return result + ":" + journal.events
}

fun foldedConstants(): String = "decimal=" + 1.0 + ":" + null

fun renamedConcatenation(startingValue: Int): String {
    val tracker = Journal(startingValue)
    val leading: String? = "start:"
    return leading + tracker.record("X") + ("/" + tracker.record("Y")) + ":" + tracker.events
}

class MutableText(var count: Int) {
    var events: String = ""

    override fun toString(): String {
        val before = count
        count += 1
        events += "T$before>"
        return "seen$before"
    }

    fun mutate(): String {
        val before = count
        count += 10
        events += "M$before>"
        return "changed$count"
    }
}

fun stringifyBeforeMutation(initialCount: Int): String {
    val value = MutableText(initialCount)
    val rendered = "item=" + value + "|" + value.mutate() + "|" + value
    return rendered + ";count=" + value.count + ";events=" + value.events
}
