package unifiedapi

import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.currentCompositeKeyHash

@Composable
fun RulePage() {
    CircularProgressIndicator()
    Text("Key: " + currentCompositeKeyHash)
}
