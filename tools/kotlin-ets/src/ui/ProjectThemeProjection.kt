@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.FqName
import java.util.Collections
import java.util.IdentityHashMap

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
    val originalReads = projectionLocalReads(body)
    var projected = false
    body.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrCall && symbolName(element.symbol.owner) == "androidx.compose.material3.MaterialTheme" &&
                sourceFile(element.symbol.owner) == null) {
                val index = element.symbol.owner.valueParameters.indexOfFirst { it.name.asString() == "colorScheme" }
                val colors = if (index >= 0) element.getValueArgument(index) else null
                val predicates = colors?.let(::androidVersionPredicates).orEmpty()
                if (colors != null && predicates.isNotEmpty()) {
                    if (hasStaticMaterialFallback(colors)) {
                        predicates.forEach {
                            it.platformCapabilityDecision = PlatformCapabilityDecision.Fallback("android.platform.version")
                            diagnostics.omitUi(it,
                                "Android SDK_INT theme guard selected the source static palette fallback",
                                "android.platform.version", "platform_capability_fallback",
                                "The target does not expose an Android SDK level. The dynamic Android palette branch is unavailable; the source static ColorScheme fallback is retained.",
                                discarded = listOf(it))
                        }
                    } else {
                        predicates.forEach {
                            it.platformCapabilityDecision = PlatformCapabilityDecision.TargetMapping("project.material.color_scheme")
                        }
                        diagnostics.omitUi(colors, "Android-version-dependent theme selection replaced with the native project palette",
                            "androidx.compose.material3.MaterialTheme.colorScheme", "project_theme_replacement",
                            "Android color selection and its private local dependencies are not evaluated; configure kotlin_ets_material_* colors in the target project. Content and typography are retained.")
                        element.putValueArgument(index, null)
                        element.usesNativeProjectTheme = true
                    }
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

private fun hasStaticMaterialFallback(expression: IrExpression): Boolean {
    val visiting = Collections.newSetFromMap(IdentityHashMap<IrDeclaration, Boolean>())
    fun inspect(value: IrExpression): Boolean = when (value) {
        is IrGetValue -> {
            val variable = value.symbol.owner as? IrVariable
            variable?.initializer?.let(::inspect) == true
        }
        is IrGetField -> value.symbol.owner.initializer?.expression?.let(::inspect) == true
        is IrTypeOperatorCall -> inspect(value.argument)
        is IrContainerExpression -> (value.statements.lastOrNull() as? IrExpression)?.let(::inspect) == true
        is IrWhen -> {
            val available = value.branches.filter { branch ->
                branch is IrElseBranch || androidVersionPredicates(branch.condition).isEmpty()
            }
            available.isNotEmpty() && available.all { inspect(it.result) }
        }
        is IrCall -> {
            val owner = value.symbol.owner
            when (symbolName(owner)) {
                "androidx.compose.material3.lightColorScheme", "androidx.compose.material3.darkColorScheme" -> true
                else -> {
                    val property = owner.correspondingPropertySymbol?.owner
                    val initializer = property?.backingField?.initializer?.expression
                    when {
                        initializer != null && visiting.add(property) -> inspect(initializer).also { visiting.remove(property) }
                        sourceFile(owner) != null && visiting.add(owner) -> {
                            val returned = when (val sourceBody = owner.body) {
                                is IrExpressionBody -> sourceBody.expression
                                is IrBlockBody -> (sourceBody.statements.singleOrNull() as? IrReturn)?.value
                                else -> null
                            }
                            (returned?.let(::inspect) == true).also { visiting.remove(owner) }
                        }
                        else -> false
                    }
                }
            }
        }
        else -> false
    }
    return inspect(expression)
}
