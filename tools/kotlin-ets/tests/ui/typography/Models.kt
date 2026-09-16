package typography
import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
fun defaults(): Typography = Typography()
fun customized(): Typography = Typography(titleSmall = TextStyle(fontSize = 23.sp, fontWeight = FontWeight.Bold))
fun selected(value: Typography): TextStyle = value.titleSmall
