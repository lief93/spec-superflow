@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import dev.ets.widgets.*
import java.net.URI
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.name.FqName

/** Closed resolved-call adapter. No native control/attribute construction or backend dependency.
 * The caller supplies ordinary language lowering and bindings for entry parameters.
 * Children are statically described; callbacks remain typed language expressions.
 */
class ComposeWidgetAdapter(private val language: Language, private val diagnostics: DiagnosticSink) {
    fun lower(function: IrSimpleFunction, scope: Scope = Scope()): Children<EtsExpression, SourceSpan> {
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        if (!function.hasAnnotation(FqName("androidx.compose.runtime.Composable")) || !function.returnType.isUnit())
            diagnostics.unsupported(function, "Widget entry requires a resolved @Composable Unit function")
        function.valueParameters.forEach { parameter ->
            if (parameter.symbol !in scope.bindings && parameter.symbol !in scope.aliases)
                diagnostics.unsupported(parameter, "Widget entry parameter requires a binding: ${parameter.name}")
        }
        return body(function.body ?: diagnostics.unsupported(function, "Widget entry has no body"), scope.fork(), function)
    }

    private fun body(body: IrBody, scope: Scope, owner: IrFunction): Children<EtsExpression, SourceSpan> = when (body) {
        is IrBlockBody -> Children(statements(body.statements, scope, owner))
        is IrExpressionBody -> Children(statements(listOf(body.expression), scope, owner))
        else -> diagnostics.unsupported(body, "Unsupported widget body")
    }

    private fun statements(statements: List<IrStatement>, scope: Scope, owner: IrFunction, terminal: Boolean = true): List<Widget<EtsExpression, SourceSpan>> =
        statements.flatMapIndexed { index, statement -> when (statement) {
            is IrVariable -> {
                val initial = statement.initializer ?: diagnostics.unsupported(statement, "Uninitialized widget local")
                if (statement.isVar) diagnostics.unsupported(statement, "Mutable widget local is outside the static widget subset")
                when {
                    initial.type.classFqName?.asString() in setOf("androidx.compose.ui.Modifier", "androidx.compose.ui.Modifier.Companion") -> modifiers(initial, scope)
                    resolve(initial, scope) is IrFunctionExpression -> Unit
                    else -> scalar(initial, scope)
                }
                scope.aliases[statement.symbol] = initial
                emptyList()
            }
            is IrCall -> listOf(widget(statement, scope))
            is IrBlock -> statements(statement.statements, scope.fork(), owner, terminal && index == statements.lastIndex)
            is IrReturn -> {
                if (statement.returnTargetSymbol.owner !== owner || !terminal || index != statements.lastIndex)
                    diagnostics.unsupported(statement, "Widget return must terminate its own children body")
                statements(listOf(statement.value), scope, owner)
            }
            is IrGetObjectValue -> if (statement.type.isUnit()) emptyList() else
                diagnostics.unsupported(statement, "Unsupported object in widget children")
            else -> diagnostics.unsupported(statement, "Unsupported widget children statement: ${statement.javaClass.simpleName}")
        } }

    private fun widget(call: IrCall, scope: Scope): Widget<EtsExpression, SourceSpan> {
        val api = symbolName(call.symbol.owner)
        if (sourceFile(call.symbol.owner) != null || !call.type.isUnit() || api !in supported)
            diagnostics.unsupported(call, "Unsupported resolved widget API: $api")
        val text = api.endsWith(".Text")
        val button = api.endsWith(".Button")
        val image = api in setOf("androidx.compose.foundation.Image", "coil.compose.AsyncImage")
        val textField = api.endsWith("TextField")
        checkArguments(call, when {
            text -> setOf("text", "modifier")
            button -> setOf("onClick", "enabled", "modifier", "content")
            image -> if (api == "androidx.compose.foundation.Image")
                setOf("painter", "contentDescription", "modifier")
            else setOf("model", "contentDescription", "modifier")
            textField -> setOf("value", "onValueChange", "modifier", "enabled")
            else -> setOf("modifier", "content")
        })
        val source = language.source(call)
        val modifier = modifiers(argument(call, "modifier"), scope)
        fun required(name: String) = argument(call, name)
            ?: diagnostics.unsupported(call, "$api requires $name")
        if (text) {
            val value = required("text")
            if (!value.type.isString()) diagnostics.unsupported(value, "Widget Text requires String text")
            return Widget.Text(widgetValue(value, scope, WidgetValueType.STRING), modifier, source)
        }
        if (image) return image(call, api, scope, modifier, source)
        if (textField) {
            val value = required("value")
            if (!value.type.isString()) diagnostics.unsupported(value,
                "Widget TextField requires a String value; rich text values are outside this subset")
            val enabled = argument(call, "enabled")?.let {
                if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget TextField enabled requires Boolean")
                scalar(it, scope)
            }
            return Widget.TextField(scalar(value, scope),
                event(required("onValueChange"), scope,
                    EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID), "TextField onValueChange"),
                enabled, modifier, source)
        }
        // A slot owns its nested scope; siblings never inherit bindings from its content.
        val content = argument(call, "content")
        val children = if (content == null && api == "androidx.compose.foundation.layout.Box" &&
            call.symbol.owner.valueParameters.none { it.name.asString() == "content" }) Children(emptyList()) else {
            val value = content ?: diagnostics.unsupported(call, "$api requires content")
            val lambda = resolve(value, scope) as? IrFunctionExpression
                ?: diagnostics.unsupported(value, "Widget children require a statically resolved lambda")
            body(lambda.function.body ?: diagnostics.unsupported(value, "Widget children have no body"), scope.fork(), lambda.function)
        }
        return when {
            button -> Widget.Button(event(required("onClick"), scope,
                EtsFunctionType(emptyList(), EtsTypes.VOID), "callback"), argument(call, "enabled")?.let {
                if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget Button enabled requires Boolean")
                scalar(it, scope)
            }, children, modifier, source)
            api.endsWith(".Row") -> Widget.Row(children, modifier, source)
            api.endsWith(".Column") -> Widget.Column(children, modifier, source)
            else -> Widget.Box(children, modifier, source)
        }
    }

    private fun image(call: IrCall, api: String, scope: Scope,
        modifiers: List<WidgetModifier<EtsExpression, SourceSpan>>, source: SourceSpan): Widget.Image<EtsExpression, SourceSpan> {
        fun required(name: String) = argument(call, name)
            ?: diagnostics.unsupported(call, "$api requires $name")
        val description = scalarImageDescription(required("contentDescription"), scope)
        val image = if (api == "androidx.compose.foundation.Image") {
            val painter = required("painter")
            val resolved = resolve(painter, scope) as? IrCall
                ?: diagnostics.unsupported(painter, "Widget Image requires direct painterResource; arbitrary Painter is unsupported")
            if (symbolName(resolved.symbol.owner) != "androidx.compose.ui.res.painterResource")
                diagnostics.unsupported(painter, "Widget Image requires direct painterResource; arbitrary Painter is unsupported")
            val value = language.expression(resolved, scope)
            val expected = EtsNamedType("Resource", external = true)
            if (value.type != expected) diagnostics.unsupported(painter,
                "Widget painterResource requires a materialized Resource value")
            ImageSource.Resource(value, language.source(resolved))
        } else {
            val model = required("model")
            if (!model.type.isString()) diagnostics.unsupported(model,
                "Widget AsyncImage requires a String URL; request and painter models are unsupported")
            val value = scalar(model, scope)
            val address = (value as? EtsLiteral)?.value as? String
            if (address != null) {
                val uri = runCatching { URI(address) }.getOrNull()
                if (uri == null || uri.scheme !in setOf("http", "https") || uri.host.isNullOrBlank() || uri.userInfo != null)
                    diagnostics.unsupported(model, "Widget AsyncImage requires an HTTP(S) URL without embedded credentials")
            }
            ImageSource.Url(value, language.source(model))
        }
        return Widget.Image(image, description, modifiers, source)
    }

    private fun scalarImageDescription(value: IrExpression, scope: Scope): EtsExpression {
        val emitted = scalar(value, scope)
        if (emitted.type !in setOf(EtsTypes.STRING, EtsTypes.NULL)) diagnostics.unsupported(value,
            "Widget Image contentDescription requires a non-null String or explicit null")
        return emitted
    }

    private fun modifiers(value: IrExpression?, scope: Scope): List<WidgetModifier<EtsExpression, SourceSpan>> {
        val expression = value?.let { resolve(it, scope) } ?: return emptyList()
        if (expression is IrGetObjectValue && sourceFile(expression.symbol.owner) == null &&
            symbolName(expression.symbol.owner) == "androidx.compose.ui.Modifier.Companion") return emptyList()
        val call = expression as? IrCall ?: diagnostics.unsupported(expression, "Unsupported widget Modifier value")
        if (sourceFile(call.symbol.owner) != null) diagnostics.unsupported(call, "Source Modifier functions require explicit widget semantics")
        val api = symbolName(call.symbol.owner)
        val receiver = call.extensionReceiver ?: call.dispatchReceiver
            ?: diagnostics.unsupported(call, "Widget Modifier requires a receiver")
        val previous = modifiers(receiver, scope)
        if (api == "androidx.compose.ui.Modifier.then") {
            checkArguments(call, setOf("other"))
            return previous + modifiers(argument(call, "other") ?: diagnostics.unsupported(call, "Modifier.then requires other"), scope)
        }
        val at = language.source(call)
        fun dimension(value: IrExpression): EtsExpression {
            if (value.type.classFqName?.asString() != "androidx.compose.ui.unit.Dp")
                diagnostics.unsupported(value, "Widget dimension requires Dp")
            val emitted = scalar(value, scope)
            if (emitted.type != EtsTypes.NUMBER) diagnostics.unsupported(value, "Widget Dp requires scalar language lowering")
            val constant = (emitted as? EtsLiteral)?.value as? Number
            if (constant != null && (!constant.toDouble().isFinite() || constant.toDouble() < 0))
                diagnostics.unsupported(value, "Widget dimension must be finite and non-negative")
            return emitted
        }
        fun required(name: String) = argument(call, name) ?: diagnostics.unsupported(call, "$api requires $name")
        val operation = when (api) {
            "androidx.compose.foundation.layout.size" -> {
                checkArguments(call, setOf("size", "width", "height"))
                val uniform = argument(call, "size")
                WidgetModifier.Size(
                    dimension(uniform ?: required("width")),
                    dimension(uniform ?: required("height")), at)
            }
            "androidx.compose.foundation.layout.width" -> {
                checkArguments(call, setOf("width")); WidgetModifier.Width(dimension(required("width")), at)
            }
            "androidx.compose.foundation.layout.height" -> {
                checkArguments(call, setOf("height")); WidgetModifier.Height(dimension(required("height")), at)
            }
            "androidx.compose.foundation.layout.padding" -> {
                checkArguments(call, setOf("all", "horizontal", "vertical", "start", "top", "end", "bottom"))
                // Reject the PaddingValues overload even when its explicit value is absent.
                if (call.symbol.owner.valueParameters.any { it.name.asString() == "paddingValues" })
                    diagnostics.unsupported(call, "PaddingValues is outside the widget subset")
                fun side(name: String, axis: String) = (argument(call, "all") ?: argument(call, name) ?: argument(call, axis))
                    ?.let(::dimension) ?: EtsLiteral(0, EtsTypes.NUMBER, at)
                WidgetModifier.Padding(side("start", "horizontal"), side("top", "vertical"),
                    side("end", "horizontal"), side("bottom", "vertical"), at)
            }
            "androidx.compose.foundation.background" -> {
                checkArguments(call, setOf("color"))
                val color = required("color")
                WidgetModifier.Background(widgetValue(color, scope, WidgetValueType.COLOR), at)
            }
            "androidx.compose.foundation.clickable" -> {
                checkArguments(call, setOf("onClick", "enabled"))
                val enabled = argument(call, "enabled")?.let {
                    if (!it.type.isBoolean()) diagnostics.unsupported(it, "Widget clickable enabled requires Boolean")
                    scalar(it, scope)
                }
                WidgetModifier.Click(event(required("onClick"), scope,
                    EtsFunctionType(emptyList(), EtsTypes.VOID), "clickable onClick"), enabled, at)
            }
            else -> diagnostics.unsupported(call, "Unsupported resolved widget Modifier API: $api")
        }
        return previous + operation
    }

    private fun resolve(value: IrExpression, scope: Scope): IrExpression = when (value) {
        is IrGetValue -> scope.aliases[value.symbol]?.let { resolve(it, scope) } ?: value
        else -> value
    }

    private fun event(value: IrExpression, scope: Scope, expected: EtsFunctionType, label: String): EtsExpression {
        val resolved = resolve(value, scope)
        if (resolved !is IrFunctionExpression && resolved !is IrGetValue)
            diagnostics.unsupported(value, "Widget $label requires a lambda or bound function value")
        val emitted = language.expression(resolved, scope)
        if (emitted.type != expected)
            diagnostics.unsupported(value, "Widget $label requires $expected")
        return emitted
    }

    private fun widgetValue(value: IrExpression, scope: Scope, type: WidgetValueType): WidgetValue<EtsExpression, SourceSpan> {
        val resolved = resolve(value, scope)
        val call = resolved as? IrCall
        val owner = call?.symbol?.owner
        val property = owner?.correspondingPropertySymbol?.owner
        val propertyName = property?.let(::symbolName)
        val api = owner?.let(::symbolName)
        val sourceOwnedToken = owner != null && property != null && sourceFile(owner) != null
        val stringResource = if (api == "androidx.compose.ui.res.stringResource") {
            val id = argument(call!!, "id")?.let { resolve(it, scope) }
            (id as? IrGetField)?.symbol?.owner?.let(::symbolName) ?: api
        } else null
        val provenance = when {
            resolved is IrConst -> WidgetValueProvenance.Literal
            api == "androidx.compose.ui.graphics.Color" -> WidgetValueProvenance.Literal
            stringResource != null -> WidgetValueProvenance.Resource(stringResource)
            propertyName?.startsWith("androidx.compose.ui.graphics.Color.Companion.") == true ->
                WidgetValueProvenance.Resource(propertyName)
            sourceOwnedToken -> WidgetValueProvenance.ThemeToken(propertyName!!)
            propertyName?.startsWith("androidx.compose.material3.MaterialTheme.") == true ||
                property?.parent?.let { it as? IrClass }?.let(::symbolName) == "androidx.compose.material3.ColorScheme" ->
                WidgetValueProvenance.ThemeToken(propertyName!!)
            else -> WidgetValueProvenance.Expression((resolved as? IrGetValue)?.symbol?.owner?.name?.asString())
        }
        val expected = when (type) {
            WidgetValueType.STRING -> EtsTypes.STRING
            WidgetValueType.COLOR -> EtsTypes.NUMBER
        }
        val emitted = if (sourceOwnedToken) {
            val adapted = adaptCall(call!!, language, scope, CallContext.VALUE) { expected }
            (adapted as? CallResult.Value)?.expression ?: diagnostics.unsupported(resolved,
                "Unmapped project widget token $propertyName; provide a project adapter mapping")
        } else if (provenance is WidgetValueProvenance.Expression) scalar(resolved, scope)
        else language.expression(resolved, scope)
        if (emitted.type != expected) diagnostics.unsupported(value,
            "Widget ${type.name.lowercase()} requires target type $expected; got ${emitted.type}")
        return WidgetValue(type, emitted, provenance, language.source(resolved))
    }

    private fun scalar(value: IrExpression, scope: Scope): EtsExpression {
        val emitted = language.expression(resolve(value, scope), scope)
        fun stable(expression: EtsExpression): Boolean = when (expression) {
            is EtsLiteral, is EtsReference -> true
            is EtsBinary -> stable(expression.left) && stable(expression.right)
            is EtsUnary -> stable(expression.operand)
            is EtsConditional -> stable(expression.condition) && stable(expression.whenTrue) && stable(expression.whenFalse)
            is EtsCall -> (expression.callee as? EtsMember)?.let { member ->
                member.name == "fround" && (member.receiver as? EtsReference)?.symbol?.id == "stdlib:Math" &&
                    expression.arguments.all(::stable)
            } == true
            else -> false
        }
        if (!stable(emitted)) diagnostics.unsupported(value,
            "Widget values require stable scalars; effectful evaluation is outside this subset")
        return emitted
    }

    private fun checkArguments(call: IrCall, supported: Set<String>) {
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            call.getValueArgument(index)?.takeIf { parameter.name.asString() !in supported }?.let {
                diagnostics.unsupported(it, "Unsupported ${symbolName(call.symbol.owner)} widget argument: ${parameter.name}")
            }
        }
    }

    private companion object {
        val supported = setOf("androidx.compose.material.Text", "androidx.compose.material3.Text",
            "androidx.compose.material.Button", "androidx.compose.material3.Button",
            "androidx.compose.foundation.Image", "coil.compose.AsyncImage",
            "androidx.compose.foundation.text.BasicTextField", "androidx.compose.material.TextField",
            "androidx.compose.material3.TextField", "androidx.compose.material3.OutlinedTextField",
            "androidx.compose.foundation.layout.Row", "androidx.compose.foundation.layout.Column",
            "androidx.compose.foundation.layout.Box")
    }
}
