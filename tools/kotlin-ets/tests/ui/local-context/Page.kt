package hostcontext

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.foundation.text.BasicText
import androidx.compose.ui.platform.LocalContext

fun identity(context: Context): Context = context
@Composable fun currentContext(): Context = LocalContext.current
@Composable fun Page() {
    val context = currentContext()
    BasicText(if (identity(context) === context) "same host" else "wrong host")
}
@Composable fun Unsupported() { BasicText(LocalContext.current.packageName) }
