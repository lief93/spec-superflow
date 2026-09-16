package longvalues
import androidx.compose.runtime.Composable
import androidx.compose.material3.Text
@Composable
fun LongPage() { Text("${identity(9007199254740993L)}") }
