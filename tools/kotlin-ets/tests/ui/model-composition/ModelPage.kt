package models.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import models.adjustSelection
import models.scenario
import models.selectedCount
import models.selectedLabel

@Composable
fun ModelPage(minimum: Int = 2, extra: Int = 1) {
    Column {
        Text(scenario(minimum, extra, true))
        if (selectedCount(-1) >= 0) {
            Text(selectedLabel())
        } else {
            Text("None")
        }
        Button(onClick = { adjustSelection(2) }) { Text("Adjust") }
    }
}
