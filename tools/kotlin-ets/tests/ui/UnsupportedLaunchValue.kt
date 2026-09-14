package negative

import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch

@Composable
fun UnknownPage() {
    val scope = rememberCoroutineScope()
    val pager = rememberPagerState { 4 }
    Button(onClick = {
        val job = scope.launch { pager.animateScrollToPage(1) }
        job.cancel()
    }) { Text("Cannot replace a source Job value with native void") }
}
