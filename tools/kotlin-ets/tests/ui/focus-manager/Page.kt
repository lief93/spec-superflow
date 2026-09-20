package focusmanager

import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusManager
import androidx.compose.ui.platform.LocalFocusManager

fun identity(manager: FocusManager): FocusManager = manager
fun dismiss(manager: FocusManager) { manager.clearFocus() }
fun used(manager: FocusManager): FocusManager {
    dismiss(manager)
    return manager
}
fun afterSoft(manager: FocusManager): String {
    manager.clearFocus(false)
    return "cleared"
}
@Composable fun currentFocus(): FocusManager = LocalFocusManager.current
@Composable fun Page() {
    val manager = used(currentFocus())
    BasicText(if (identity(manager) === manager) "same host" else "wrong host")
}
@Composable fun Unsupported() {
    BasicText(if (LocalFocusManager.current.moveFocus(FocusDirection.Down)) "moved" else "stuck")
}
@Composable fun SoftClear() { BasicText(afterSoft(LocalFocusManager.current)) }
