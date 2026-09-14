package negative

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun getRawString(key: String): String = MaterialTheme.typography.toString() + key

@Composable
fun UnknownPage() { Text(getRawString("theme")) }
