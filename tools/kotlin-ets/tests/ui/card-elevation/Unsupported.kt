package cardelevation.unsupported

import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

private var count = 0
private fun nextElevation(): Dp {
    count += 1
    return count.dp
}

@Composable
fun DynamicPage() {
    Card(elevation = CardDefaults.cardElevation(defaultElevation = nextElevation())) { Text("Dynamic") }
}

@Composable
fun RuntimePage(raised: Boolean = true) {
    val elevation = if (raised) CardDefaults.cardElevation(1.dp) else CardDefaults.cardElevation(2.dp)
    Card(elevation = elevation) { Text("Runtime") }
}

@Composable
fun InteractivePage() {
    Card(onClick = {}, elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)) { Text("Interactive") }
}
