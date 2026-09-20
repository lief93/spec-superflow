package clickabletext

import androidx.compose.foundation.text.ClickableText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle

@Composable
fun Page() {
    val count = remember { mutableStateOf(0) }
    val annotated = buildAnnotatedString {
        append("Don't have an account?")
        pushStringAnnotation(tag = "Sign Up", annotation = "Sign Up")
        withStyle(SpanStyle(color = Color.Red, fontWeight = FontWeight.SemiBold)) {
            append("Sign Up")
        }
    }
    ClickableText(
        text = annotated,
        style = TextStyle(color = Color.Gray, fontWeight = FontWeight.Normal),
        onClick = { offset ->
            annotated.getStringAnnotations(offset, offset).firstOrNull()?.let {
                count.value = count.value + 1
            }
        }
    )
}

@Composable
fun UnsupportedTag() {
    val annotated = buildAnnotatedString { append("A") }
    ClickableText(text = annotated, onClick = { offset ->
        annotated.getStringAnnotations("tag", offset, offset)
    })
}
