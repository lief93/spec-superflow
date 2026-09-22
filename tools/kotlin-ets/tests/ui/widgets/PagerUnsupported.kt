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
fun UnsupportedPagerArgument() {
    val pager = rememberPagerState { 3 }
    HorizontalPager(state = pager, userScrollEnabled = false) { page -> Text("Page $page") }
}
