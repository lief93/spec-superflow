package negative

import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun UnknownPage() {
    val pager = rememberPagerState { 0 }
    HorizontalPager(state = pager) { page -> Text("Page $page") }
}
