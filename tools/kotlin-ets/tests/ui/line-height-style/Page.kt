package lineheightstyle

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ProvideTextStyle
import androidx.compose.material3.Text
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.sp

private val UnsupportedStyle = TextStyle(
    lineHeight = 24.sp,
    lineHeightStyle = LineHeightStyle(
        alignment = LineHeightStyle.Alignment.Bottom,
        trim = LineHeightStyle.Trim.LastLineBottom,
        mode = LineHeightStyle.Mode.Fixed,
    ),
)

private val AppTypography = Typography(bodyLarge = UnsupportedStyle)

@Composable
fun Page() {
    MaterialTheme(typography = AppTypography) {
        Text("Theme style", style = MaterialTheme.typography.bodyLarge)
        ProvideTextStyle(UnsupportedStyle) {
            Text("Provided style")
        }
    }
}

@Composable
fun SupportedPage() {
    Text(
        "Supported style",
        style = TextStyle(
            lineHeight = 24.sp,
            lineHeightStyle = LineHeightStyle(
                alignment = LineHeightStyle.Alignment.Center,
                trim = LineHeightStyle.Trim.None,
                mode = LineHeightStyle.Mode.Fixed,
            ),
        ),
    )
}
