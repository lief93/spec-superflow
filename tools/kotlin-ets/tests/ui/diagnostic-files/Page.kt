package diagnosticfiles

import androidx.compose.runtime.Composable

@Composable
fun RequiredPage(state: Int) { Label() }

@Composable
fun DefaultPage(text: String = System.getProperty("title")) { Label() }
