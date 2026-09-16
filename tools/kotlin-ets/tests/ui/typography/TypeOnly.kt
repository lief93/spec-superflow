package typography
import androidx.compose.material3.Typography
import androidx.compose.material3.MaterialTheme
fun ignore(value: Typography) {}
fun nested(value: List<Typography?>) {}
fun identity(value: MaterialTheme): MaterialTheme = value
