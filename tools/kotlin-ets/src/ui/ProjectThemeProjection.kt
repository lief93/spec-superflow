@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.FqName

internal var IrCall.usesNativeProjectTheme: Boolean? by irAttribute(followAttributeOwner = true)

/** Project policy replaces an Android-only configuration value, never its content lambda. */
internal fun projectAndroidTheme(declaration: IrDeclaration, diagnostics: DiagnosticSink) {
    if (!diagnostics.reportUiDegradation) return
    val previousFile = diagnostics.currentFile
    diagnostics.currentFile = sourceFile(declaration)?.fileEntry?.name
    try {
        declaration.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitSimpleFunction(declaration: IrSimpleFunction) {
                if (declaration.hasAnnotation(FqName("androidx.compose.runtime.Composable")) && declaration.returnType.isUnit()) {
                    (declaration.body as? IrBlockBody)?.let { projectThemeBody(it, diagnostics) }
                }
                declaration.acceptChildrenVoid(this)
            }
        })
    } finally { diagnostics.currentFile = previousFile }
}

private fun projectThemeBody(body: IrBlockBody, diagnostics: DiagnosticSink) {
    fun dependsOnAndroidVersion(element: IrElement, visited: MutableSet<IrValueSymbol> = mutableSetOf()): Boolean {
        var found = false
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrGetField && symbolName(element.symbol.owner) == "android.os.Build.VERSION.SDK_INT" &&
                    sourceFile(element.symbol.owner) == null) found = true
                if (element is IrGetValue && visited.add(element.symbol)) {
                    val local = element.symbol.owner as? IrVariable
                    if (local != null && !local.isVar && local.initializer?.let { dependsOnAndroidVersion(it, visited) } == true) found = true
                }
                element.acceptChildrenVoid(this)
            }
        })
        return found
    }
    val originalReads = projectionLocalReads(body)
    var projected = false
    body.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrCall && symbolName(element.symbol.owner) == "androidx.compose.material3.MaterialTheme" &&
                sourceFile(element.symbol.owner) == null) {
                val index = element.symbol.owner.valueParameters.indexOfFirst { it.name.asString() == "colorScheme" }
                val colors = if (index >= 0) element.getValueArgument(index) else null
                if (colors != null && dependsOnAndroidVersion(colors)) {
                    diagnostics.omitUi(colors, "Android-version-dependent theme selection replaced with the native project palette",
                        "androidx.compose.material3.MaterialTheme.colorScheme", "project_theme_replacement",
                        "Android color selection and its private local dependencies are not evaluated; configure kotlin_ets_material_* colors in the target project. Content and typography are retained.")
                    element.putValueArgument(index, null)
                    element.usesNativeProjectTheme = true
                    projected = true
                }
            }
            element.acceptChildrenVoid(this)
        }
    })
    if (!projected) return

    fun systemBarEffect(call: IrCall): Boolean {
        val action = argument(call, "effect") as? IrFunctionExpression ?: return false
        var supported = true
        var writesSystemBar = false
        action.function.body?.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall) {
                    val function = element.symbol.owner
                    val name = symbolName(function)
                    val setter = name in setOf("android.view.Window.setStatusBarColor", "android.view.Window.setNavigationBarColor",
                        "androidx.core.view.WindowInsetsControllerCompat.setAppearanceLightStatusBars",
                        "androidx.core.view.WindowInsetsControllerCompat.setAppearanceLightNavigationBars")
                    writesSystemBar = writesSystemBar || setter
                    val property = function.correspondingPropertySymbol?.owner
                    val paletteRead = property != null && property.getter?.symbol == function.symbol &&
                        (property.parent as? IrClass)?.let(::symbolName) == "androidx.compose.material3.ColorScheme"
                    if (sourceFile(function) != null || !setter && !paletteRead && name !in setOf(
                            "android.app.Activity.getWindow", "android.view.View.getContext",
                            "androidx.core.view.WindowCompat.getInsetsController", "androidx.compose.ui.graphics.toArgb",
                            "kotlin.Boolean.not")) supported = false
                }
                if (element is IrSetValue || element is IrSetField) supported = false
                element.acceptChildrenVoid(this)
            }
        }) ?: return false
        return supported && writesSystemBar
    }

    // A guard with no remaining UI can be discarded together with the omitted effect.
    fun onlyEffects(element: IrElement): Boolean = when (element) {
        is IrCall -> sourceFile(element.symbol.owner) == null && symbolName(element.symbol.owner) == "androidx.compose.runtime.SideEffect" && systemBarEffect(element)
        is IrWhen -> element.branches.all { onlyEffects(it.result) }
        is IrContainerExpression -> element.statements.all { onlyEffects(it) }
        is IrGetObjectValue -> element.type.isUnit()
        is IrConst -> element.type.isUnit()
        else -> false
    }
    fun containsEffect(element: IrElement): Boolean {
        var found = false
        element.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall && symbolName(element.symbol.owner) == "androidx.compose.runtime.SideEffect" &&
                    sourceFile(element.symbol.owner) == null) found = true
                element.acceptChildrenVoid(this)
            }
        })
        return found
    }
    body.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            val statements = when (element) {
                is IrBlockBody -> element.statements
                is IrContainerExpression -> element.statements
                else -> null
            }
            statements?.removeAll { statement ->
                if (onlyEffects(statement) && containsEffect(statement)) {
                    diagnostics.omitUi(statement, "Theme SideEffect and its guard omitted",
                        "androidx.compose.runtime.SideEffect", "omitted_theme_effect",
                        "The effect, guard and their private local dependencies are not evaluated; Android system-bar configuration is not migrated.")
                    true
                } else false
            }
            element.acceptChildrenVoid(this)
        }
    })
    // Only prune locals that became unused because of this projection, not arbitrary
    // unused declarations or file initializers (which may have observable effects).
    pruneProjectedLocals(body, originalReads, diagnostics)
}
