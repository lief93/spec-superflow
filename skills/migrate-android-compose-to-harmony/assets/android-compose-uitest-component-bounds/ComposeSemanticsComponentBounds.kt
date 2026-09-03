package androidtoharmony.visual

import android.graphics.Bitmap
import android.os.Bundle
import android.graphics.Rect as AndroidRect
import android.os.Build
import android.view.WindowInsets
import androidx.compose.ui.geometry.Rect
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.runner.lifecycle.ActivityLifecycleMonitorRegistry
import androidx.test.runner.lifecycle.Stage
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import kotlin.math.ceil
import kotlin.math.floor

private const val COMPONENT_BOUNDS_SCHEMA = "android-to-harmony.component-bounds.v2"
private const val MARKER = "ANDROID_COMPONENT_BOUNDS:"
private val SAFE_TOKEN = Regex("^[A-Za-z0-9._:/#@-]{1,120}$")

data class ComposeSemanticsComponentBoundsDescriptor(
    val testTag: String,
    val type: String,
    val semanticKey: String,
)

fun captureComposeSemanticsComponentBoundsAndScreenshot(
    screenshotFile: File,
    composeRootX: Int,
    composeRootY: Int,
    descriptors: List<ComposeSemanticsComponentBoundsDescriptor>,
    boundsForTag: (String) -> Rect?,
): String {
    require(!screenshotFile.exists()) { "screenshot output already exists" }
    require(screenshotFile.parentFile?.isDirectory == true) {
        "screenshot parent must be an existing directory"
    }

    val instrumentation = InstrumentationRegistry.getInstrumentation()
    val uiAutomation = instrumentation.uiAutomation
    val screenshot = requireNotNull(uiAutomation.takeScreenshot()) {
        "device screenshot was not captured"
    }
    val contentInsets = captureContentInsets()
    val components = JSONArray()

    descriptors.forEach { descriptor ->
        if (
            SAFE_TOKEN.matches(descriptor.testTag) &&
            SAFE_TOKEN.matches(descriptor.type) &&
            SAFE_TOKEN.matches(descriptor.semanticKey)
        ) {
            val bounds = boundsForTag(descriptor.testTag)
            if (bounds != null) {
                val left = (composeRootX + floor(bounds.left).toInt()).coerceAtLeast(0)
                val top = (composeRootY + floor(bounds.top).toInt()).coerceAtLeast(0)
                val right = (composeRootX + ceil(bounds.right).toInt()).coerceAtMost(screenshot.width)
                val bottom = (composeRootY + ceil(bounds.bottom).toInt()).coerceAtMost(screenshot.height)
                if (left < right && top < bottom) {
                    components.put(
                        JSONObject()
                            .put("id", descriptor.testTag)
                            .put("type", descriptor.type)
                            .put("semantic_key", descriptor.semanticKey)
                            .put(
                                "bounds",
                                JSONObject()
                                    .put("x", left)
                                    .put("y", top)
                                    .put("width", right - left)
                                    .put("height", bottom - top),
                            ),
                    )
                }
            }
        }
    }

    FileOutputStream(screenshotFile).use { output ->
        check(screenshot.compress(Bitmap.CompressFormat.PNG, 100, output)) {
            "device screenshot was not written"
        }
    }

    val inventory = JSONObject()
        .put("schema", COMPONENT_BOUNDS_SCHEMA)
        .put(
            "screenshot_dimensions",
            JSONObject().put("width", screenshot.width).put("height", screenshot.height),
        )
        .put(
            "content_insets_px",
            JSONObject()
                .put("left", contentInsets.left)
                .put("top", contentInsets.top)
                .put("right", contentInsets.right)
                .put("bottom", contentInsets.bottom),
        )
        .put("components", components)
    val marker = MARKER + inventory.toString()
    instrumentation.sendStatus(
        2,
        Bundle().apply { putString("stream", "$marker\n") },
    )
    return marker
}

private fun captureContentInsets(): AndroidRect {
    check(Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
        "automatic content insets require Android 6.0 or newer"
    }
    val instrumentation = InstrumentationRegistry.getInstrumentation()
    var captured: AndroidRect? = null
    instrumentation.runOnMainSync {
        val activity = ActivityLifecycleMonitorRegistry.getInstance()
            .getActivitiesInStage(Stage.RESUMED)
            .singleOrNull()
        val windowInsets = activity?.window?.decorView?.rootWindowInsets
        if (windowInsets != null) {
            captured = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                val insets = windowInsets.getInsets(
                    WindowInsets.Type.systemBars() or WindowInsets.Type.displayCutout(),
                )
                AndroidRect(insets.left, insets.top, insets.right, insets.bottom)
            } else {
                @Suppress("DEPRECATION")
                AndroidRect(
                    windowInsets.systemWindowInsetLeft,
                    windowInsets.systemWindowInsetTop,
                    windowInsets.systemWindowInsetRight,
                    windowInsets.systemWindowInsetBottom,
                )
            }
        }
    }
    return requireNotNull(captured) { "runtime window insets were not available" }
}
