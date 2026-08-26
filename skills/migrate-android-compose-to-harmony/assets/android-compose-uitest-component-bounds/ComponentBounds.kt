package androidtoharmony.visual

import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.platform.app.InstrumentationRegistry
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileOutputStream
import java.util.ArrayDeque

private const val COMPONENT_BOUNDS_SCHEMA = "android-to-harmony.component-bounds.v1"
private const val MARKER = "ANDROID_COMPONENT_BOUNDS:"
private val SAFE_TOKEN = Regex("^[A-Za-z0-9._:/#@-]{1,120}$")

data class ComponentBoundsDescriptor(
    val testTag: String,
    val type: String,
    val semanticKey: String,
)

fun captureComponentBoundsAndScreenshot(
    screenshotFile: File,
    descriptors: List<ComponentBoundsDescriptor>,
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
    val root = requireNotNull(uiAutomation.rootInActiveWindow) {
        "active accessibility window was not available"
    }
    val components = JSONArray()

    descriptors.forEach { descriptor ->
        if (
            SAFE_TOKEN.matches(descriptor.testTag) &&
            SAFE_TOKEN.matches(descriptor.type) &&
            SAFE_TOKEN.matches(descriptor.semanticKey)
        ) {
            val matches = findNodesByTag(root, descriptor.testTag)
            if (matches.size == 1) {
                val bounds = Rect()
                matches.single().getBoundsInScreen(bounds)
                val left = bounds.left.coerceAtLeast(0)
                val top = bounds.top.coerceAtLeast(0)
                val right = bounds.right.coerceAtMost(screenshot.width)
                val bottom = bounds.bottom.coerceAtMost(screenshot.height)
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
        .put("components", components)
    val marker = MARKER + inventory.toString()
    instrumentation.sendStatus(
        2,
        Bundle().apply { putString("stream", "$marker\n") },
    )
    return marker
}

private fun findNodesByTag(
    root: AccessibilityNodeInfo,
    testTag: String,
): List<AccessibilityNodeInfo> {
    val matches = mutableListOf<AccessibilityNodeInfo>()
    val queue = ArrayDeque<AccessibilityNodeInfo>()
    queue.add(root)
    while (queue.isNotEmpty()) {
        val node = queue.removeFirst()
        val resourceId = node.viewIdResourceName
        if (resourceId == testTag || resourceId?.endsWith(":id/$testTag") == true) {
            matches.add(node)
        }
        for (index in 0 until node.childCount) {
            node.getChild(index)?.let(queue::addLast)
        }
    }
    return matches
}
