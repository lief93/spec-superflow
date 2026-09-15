@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.isUnit
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid
import org.jetbrains.kotlin.name.FqName

// Material3 1.3.2 TypeScaleTokens; the page host supplies default MaterialTheme.
internal enum class MaterialTextContext(val size: Int, val lineHeight: Int, val weight: Int, val tracking: Double) {
    BodyLarge(16, 24, 400, 0.5), LabelLarge(14, 20, 500, 0.1)
}

/** Resolve slot invocation context, not the lexical context where its closure was created. */
internal fun materialTextContexts(root: IrSimpleFunction, diagnostics: DiagnosticSink): Map<IrFunction, MaterialTextContext> {
    val contexts = linkedMapOf<IrFunction, MaterialTextContext>()
    val active = mutableSetOf<IrFunction>()
    val composable = FqName("androidx.compose.runtime.Composable")
    fun scan(function: IrFunction, scope: Scope, context: MaterialTextContext) {
        val previousFile = diagnostics.currentFile
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        val previous = contexts.put(function, context)
        if (previous != null && previous != context)
            diagnostics.unsupported(function, "Source builder used with different inherited Material text styles")
        if (!active.add(function)) diagnostics.unsupported(function, "Recursive UI text context is unsupported")
        try {
            function.body?.acceptVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
            override fun visitVariable(declaration: IrVariable) {
                declaration.initializer?.let { scope.aliases[declaration.symbol] = it }
                declaration.acceptChildrenVoid(this)
            }
            override fun visitFunctionExpression(expression: IrFunctionExpression) {
                scan(expression.function, scope.fork(), context)
            }
            override fun visitCall(expression: IrCall) {
                val target = expression.symbol.owner
                val api = symbolName(target)
                if (target.name.asString() == "invoke") {
                    val content = lambda(expression.dispatchReceiver, scope)
                    if (content != null) {
                        scan(content, scope.fork(), context)
                        return
                    }
                }
                if (target.hasAnnotation(composable) && target.returnType.isUnit() &&
                    sourceFile(target) != null && !target.isExternal) {
                    val child = scope.fork()
                    target.valueParameters.forEachIndexed { index, parameter ->
                        val value = expression.getValueArgument(index) ?: parameter.defaultValue?.expression
                        if (value != null) child.aliases[parameter.symbol] = value
                    }
                    scan(target, child, context)
                    return
                }
                if (api == "androidx.compose.material3.Button" || api == "androidx.compose.material3.MaterialTheme") {
                    val content = lambda(argument(expression, "content"), scope)
                        ?: diagnostics.unsupported(expression, "Button requires source content")
                    scan(content, scope.fork(), if (api == "androidx.compose.material3.Button") MaterialTextContext.LabelLarge else MaterialTextContext.BodyLarge)
                    return
                }
                // External controls/adapters can receive an existing slot, not
                // only a literal lambda visible to the child visitor.
                target.valueParameters.forEachIndexed { index, parameter ->
                    val value = expression.getValueArgument(index)
                    if (parameter.type.hasAnnotation(composable) && value !is IrFunctionExpression) {
                        lambda(value, scope)?.let { scan(it, scope.fork(), context) }
                    }
                }
                expression.acceptChildrenVoid(this)
            }
            })
        } finally {
            active.remove(function)
            diagnostics.currentFile = previousFile
        }
    }
    scan(root, Scope(), MaterialTextContext.BodyLarge)
    return contexts
}
