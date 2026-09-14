package negative

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun SharedLabel() { Text("Shared") }

@Composable
fun UnknownPage() {
    Column {
        SharedLabel()
        Button(onClick = {}) { SharedLabel() }
    }
}
