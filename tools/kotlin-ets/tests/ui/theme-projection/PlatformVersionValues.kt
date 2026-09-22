package themeprojection

import android.os.Build
import androidx.annotation.ChecksSdkIntAtLeast

@ChecksSdkIntAtLeast(api = Build.VERSION_CODES.S)
fun supportsDynamicTheming(): Boolean = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S

fun platformFallbackLabel(): String =
    if (supportsDynamicTheming()) "mapped" else "fallback"
