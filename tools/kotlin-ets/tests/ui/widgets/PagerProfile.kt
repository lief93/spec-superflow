package widgetpager

import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable

@Composable
fun PagerProfile() {
    val pager = rememberPagerState(initialPage = 1) { 3 }
    HorizontalPager(state = pager) { page ->
        Text("Current ${pager.currentPage}: Page $page")
    }
}

@Composable
fun FivePageProfile() {
    val pager = rememberPagerState(initialPage = 4) { 5 }
    HorizontalPager(state = pager) { page ->
        Text("Page $page")
    }
}
