package unifiedapi

import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.currentCompositeKeyHash

@Composable
fun RulePage() {
    HorizontalDivider()
    Text("Key: " + currentCompositeKeyHash)
}
