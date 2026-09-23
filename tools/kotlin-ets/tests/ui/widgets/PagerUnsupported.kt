package widgetpager

import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun DynamicPageCount(pages: Int = 3) {
    val pager = rememberPagerState { pages }
    HorizontalPager(state = pager) { page -> Text("Page $page") }
}

@Composable
fun EmptyPageCount() {
    val pager = rememberPagerState { 0 }
    HorizontalPager(state = pager) { page -> Text("Page $page") }
}

@Composable
fun OutOfBoundsInitialPage() {
    val pager = rememberPagerState(initialPage = 3) { 3 }
    HorizontalPager(state = pager) { page -> Text("Page $page") }
}

@Composable
fun InlinePagerState() {
    HorizontalPager(state = rememberPagerState { 4 }) { page -> Text("Page $page") }
}

@Composable
fun ReversePager() {
    val pager = rememberPagerState { 4 }
    HorizontalPager(state = pager, reverseLayout = true) { page -> Text("Page $page") }
}
