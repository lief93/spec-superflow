package sample

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

class Model(val title: String, val detail: String)

fun buttonLabel(page: Int): String = if (page == 3) "Finish" else "Continue"

fun pageModel(page: Int): Model = Model(
    "Chapter " + (page + 1),
    when (page) {
        0 -> "Observe the world around you."
        1 -> "Collect one small discovery."
        2 -> "Connect it with a new idea."
        else -> "Take your next step."
    }
)

@Composable
fun PageFrame(title: String, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxSize().background(Color(0xFFF7F5EF)).padding(20.dp)) {
        Text(title, fontSize = 24.sp, color = Color.Black)
        Spacer(Modifier.height(12.dp))
        content()
    }
}

@Composable
fun ContentPanel(spacing: Int, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Spacer(Modifier.height(spacing.dp).testTag("computed-spacing"))
        content()
    }
}

@Composable
fun Page(base: Int = 12, extra: Int = 4) {
    val pagerState = rememberPagerState { 4 }
    val callbackCount = remember { mutableStateOf(0) }
    val scope = rememberCoroutineScope()
    PageFrame("Field Notes") {
        ContentPanel(base + extra) {
            HorizontalPager(
                state = pagerState,
                modifier = Modifier.fillMaxWidth().height(240.dp).testTag("pager")
            ) { page ->
                val model = pageModel(page)
                Column(Modifier.fillMaxSize().padding(16.dp).testTag("page-" + page)) {
                    Text(model.title, fontSize = 20.sp, color = Color.Black)
                    Spacer(Modifier.height((base + extra).dp))
                    Text(model.detail, fontSize = 16.sp, color = Color.Black)
                }
            }
            Row(Modifier.padding(8.dp)) {
                repeat(4) { index ->
                    Box(
                        Modifier.padding(4.dp).width(20.dp).height(8.dp)
                            .background(if (pagerState.currentPage == index) Color.Black else Color.Gray)
                            .testTag("indicator-" + index)
                            .clickable {
                                scope.launch { pagerState.animateScrollToPage(index) }
                            }
                    )
                }
            }
            Text("Page " + (pagerState.currentPage + 1) + " of " + pagerState.pageCount, color = Color.Black)
            Text("Callback " + callbackCount.value, Modifier.testTag("callback-value"), color = Color.Black)
            Button(
                onClick = {
                    callbackCount.value = callbackCount.value + 1
                    scope.launch {
                        pagerState.animateScrollToPage((pagerState.currentPage + 1) % pagerState.pageCount)
                    }
                },
                modifier = Modifier.fillMaxWidth().height(48.dp).testTag("action-button")
            ) {
                Text(buttonLabel(pagerState.currentPage), fontSize = 16.sp)
            }
        }
    }
}
