package alignment

import androidx.compose.runtime.Composable
import androidx.compose.foundation.layout.Box
import androidx.compose.ui.BiasAlignment

@Composable fun Custom() { Box(contentAlignment = BiasAlignment(0.25f, 0.5f)) {} }
