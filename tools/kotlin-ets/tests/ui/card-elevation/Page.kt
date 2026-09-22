package cardelevation

import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

private val Raised = CardDefaults.cardElevation(defaultElevation = 8.dp)

@Composable
fun Page() {
    Card(
        modifier = Modifier.width(80.dp).height(40.dp),
        shape = RoundedCornerShape(4.dp),
        elevation = Raised,
    ) {
        Text("First")
        Text("Second")
    }
    Card(elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)) {
        Text("Flat")
    }
}
