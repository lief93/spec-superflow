package values

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

class Counter(var value: Int) {
    fun next(): String {
        value = value + 1
        return "Value " + value
    }
}

@Composable
fun SourceValues() {
    val counter = Counter(0)
    val label = counter.next()
    val unused = counter.next()
    Column {
        Text(label)
        Text(label)
        Text("Count " + counter.value)
    }
}
