@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.widgets.*
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    val imageFile = File(args[2])
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(3)) { module ->
        val sink = DiagnosticSink()
        val imageResources = ImageResources(
            mapOf("widgetsfixture.R.drawable.logo" to "widget_logo"),
            mapOf("widgetsfixture.R.drawable.logo" to imageFile),
            mapOf("widgetsfixture.R.drawable.logo" to 0x7f010001),
        )
        val strings = StringResources(mapOf("base" to mapOf(
            "widgetsfixture.R.string.title" to "Resource title",
            "widgetsfixture.R.string.action" to "Resource action",
        )))
        val projectTokens = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                return when (property) {
                    "widgetsfixture.KnownTokens.label" -> EtsLiteral("Known label", EtsTypes.STRING, language.source(call))
                    "widgetsfixture.KnownTokens.brand" -> EtsLiteral(0xFF336699L, EtsTypes.NUMBER, language.source(call))
                    else -> null
                }
            }
        }
        val language = EtsBackend(sink,
            listOf(projectTokens, StandardLibraryRules(), ComposeColorValueRule(), ComposeDimensionRule(),
                imageResources, strings)).language
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val page = functions.single { it.fqNameWhenAvailable?.asString() == "widgetsfixture.Page" }
        val scope = Scope()
        val parameters = page.valueParameters.map { parameter ->
            val symbol = EtsSymbol("widget-input:${parameter.name}", parameter.name.asString(), language.type(parameter.type), language.source(parameter))
            scope.bindings[parameter.symbol] = EtsReference(symbol)
            EtsParameter(symbol)
        }
        val adapter = ComposeWidgetAdapter(language, sink)
        val model = adapter.lower(page, scope)
        val column = model.widgets.single() as Widget.Column
        check(column.modifiers.map { it.javaClass.simpleName } == listOf("Width", "Padding", "Width"))
        check((column.modifiers[0] as WidgetModifier.Width).value.let { it as EtsLiteral }.value == 120.0)
        check((column.modifiers[2] as WidgetModifier.Width).value.let { it as EtsLiteral }.value == 80.0)
        check(column.children.widgets.size == 12)
        val title = column.children.widgets[0] as Widget.Text
        check(title.text.type == WidgetValueType.STRING)
        check(title.text.provenance == WidgetValueProvenance.Expression("title"))
        check((title.text.value as EtsReference).symbol == parameters[0].symbol)
        val resourceTitle = column.children.widgets[1] as Widget.Text
        check(resourceTitle.text.provenance == WidgetValueProvenance.Resource("widgetsfixture.R.string.title"))
        check(resourceTitle.text.value.type == EtsTypes.STRING)
        val tokenTitle = column.children.widgets[2] as Widget.Text
        check(tokenTitle.text.provenance == WidgetValueProvenance.ThemeToken("widgetsfixture.KnownTokens.label"))
        check((tokenTitle.text.value as EtsLiteral).value == "Known label")
        val button = column.children.widgets[3] as Widget.Button
        check((button.onClick as EtsReference).symbol == parameters[2].symbol)
        check((button.enabled as EtsReference).symbol == parameters[1].symbol)
        check(button.modifiers.map { it.javaClass.simpleName } == listOf("Background", "Padding", "Height"))
        val buttonBackground = button.modifiers[0] as WidgetModifier.Background
        check(buttonBackground.color.provenance == WidgetValueProvenance.ThemeToken("widgetsfixture.KnownTokens.brand"))
        check((buttonBackground.color.value as EtsLiteral).value == 0xFF336699L)
        val row = button.content.widgets.single() as Widget.Row
        check(row.children.widgets.size == 2)
        val buttonLabel = row.children.widgets[0] as Widget.Text
        check(buttonLabel.text.provenance == WidgetValueProvenance.Resource("widgetsfixture.R.string.action"))
        val box = row.children.widgets[1] as Widget.Box
        check(box.children.widgets.single() is Widget.Text)
        check(box.modifiers.map { it.javaClass.simpleName } == listOf("Height", "Width"))
        val literalText = (column.children.widgets[4] as Widget.Text).text
        check(literalText.provenance == WidgetValueProvenance.Literal)
        check((literalText.value as EtsLiteral).value == "after")
        val coloredRow = column.children.widgets[5] as Widget.Row
        check(coloredRow.modifiers.map { it.javaClass.simpleName } == listOf("Padding", "Width", "Background"))
        val resourceColor = (coloredRow.modifiers[2] as WidgetModifier.Background).color
        check(resourceColor.provenance == WidgetValueProvenance.Resource("androidx.compose.ui.graphics.Color.Companion.Red"))
        check(resourceColor.value.type == EtsTypes.NUMBER)
        val emptyBox = column.children.widgets[6] as Widget.Box
        check(emptyBox.children.widgets.isEmpty())
        val literalColor = (emptyBox.modifiers[1] as WidgetModifier.Background).color
        check(literalColor.provenance == WidgetValueProvenance.Literal && literalColor.value.type == EtsTypes.NUMBER)
        val styledText = column.children.widgets[7] as Widget.Text
        check(styledText.modifiers.map { it.javaClass.simpleName } == listOf("Size", "Background", "Click", "Padding"))
        val styledSize = styledText.modifiers[0] as WidgetModifier.Size
        check((styledSize.width as EtsLiteral).value == 36.0 && (styledSize.height as EtsLiteral).value == 20.0)
        val expressionColor = (styledText.modifiers[1] as WidgetModifier.Background).color
        check(expressionColor.provenance == WidgetValueProvenance.Expression("surfaceColor"))
        check((expressionColor.value as EtsReference).symbol == parameters[6].symbol)
        val styledClick = styledText.modifiers[2] as WidgetModifier.Click
        check((styledClick.onClick as EtsReference).symbol == parameters[2].symbol)
        check((styledClick.enabled as EtsReference).symbol == parameters[1].symbol)
        val resourceImage = column.children.widgets[8] as Widget.Image
        val resourceSource = resourceImage.image as ImageSource.Resource
        check((resourceSource.value as EtsCall).let {
            (it.callee as EtsReference).symbol.name == "\$r" &&
                (it.arguments.single() as EtsLiteral).value == "app.media.widget_logo"
        })
        check((resourceImage.contentDescription as EtsLiteral).value == "Local image")
        check(resourceImage.modifiers.map { it.javaClass.simpleName } == listOf("Click", "Background", "Size"))
        val imageClick = resourceImage.modifiers[0] as WidgetModifier.Click
        check((imageClick.onClick as EtsReference).symbol == parameters[2].symbol)
        check((imageClick.enabled as EtsReference).symbol == parameters[1].symbol)
        check((((resourceImage.modifiers[1] as WidgetModifier.Background).color.value) as EtsReference).symbol == parameters[6].symbol)
        val imageSize = resourceImage.modifiers[2] as WidgetModifier.Size
        check((imageSize.width as EtsLiteral).value == 24.0 && imageSize.width == imageSize.height)
        val urlImage = column.children.widgets[9] as Widget.Image
        val urlSource = urlImage.image as ImageSource.Url
        check((urlSource.value as EtsReference).symbol == parameters[3].symbol)
        check((urlImage.contentDescription as EtsLiteral).value == null)
        val materialField = column.children.widgets[10] as Widget.TextField
        val basicField = column.children.widgets[11] as Widget.TextField
        for (field in listOf(materialField, basicField)) {
            check((field.value as EtsReference).symbol == parameters[4].symbol)
            check((field.onValueChange as EtsReference).symbol == parameters[5].symbol)
            check((field.enabled as EtsReference).symbol == parameters[1].symbol)
        }
        check(column.source.file!!.endsWith("/Page.kt") && column.source.start >= 0 && column.source.end > column.source.start)
        File(output, "model.txt").writeText(model.toString())
        val children = HarmonyWidgetBackend().lower(model)
        val at = language.source(page)
        val builder = EtsFunction("Page", parameters, EtsTypes.VOID, children, at, exported = true, builder = true)
        val changed = EtsParameter(EtsSymbol("widget-entry:changed", "changed", EtsTypes.STRING, at))
        val content = EtsUiElement(EtsCall(EtsReference(builder.symbol), listOf(
            EtsLiteral("resolved", EtsTypes.STRING, at), EtsLiteral(true, EtsTypes.BOOLEAN, at),
            EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, at),
            EtsLiteral("https://example.invalid/widget.png", EtsTypes.STRING, at),
            EtsLiteral("input", EtsTypes.STRING, at),
            EtsLambda(listOf(changed), emptyList(), EtsTypes.VOID, at),
            EtsLiteral(0xFF112233L, EtsTypes.NUMBER, at)), EtsTypes.VOID, at))
        // The SDK requires an entry container. It is itself a semantic Box.
        val shell = HarmonyWidgetBackend().lower(Widget.Box(Children(emptyList()), emptyList(), at)).copy(children = listOf(content))
        val entry = EtsClass("WidgetPage", listOf(EtsFunction("build", emptyList(), EtsTypes.VOID,
            listOf(shell), at, kind = EtsFunctionKind.METHOD, build = true)), at, exported = true, component = true, entry = true)
        val program = EtsProgram(listOf(EtsFile(at.file!!, listOf(builder, entry))))
        EtsValidator().validate(program)
        File(output, "WidgetPage.ets").writeText(emitEtsProgram(program, StandardLibraryRuntime))
        for ((relative, source) in imageResources.artifacts()) {
            val target = File(output, "WidgetPage.ets.resources/$relative")
            target.parentFile.mkdirs()
            source.copyTo(target)
        }
        for ((relative, contents) in strings.artifacts()) {
            val target = File(output, "WidgetPage.ets.resources/$relative")
            target.parentFile.mkdirs()
            target.writeText(contents)
        }
        val tree = mutableListOf<EtsNode>()
        walkEts(builder, tree::add)
        val elements = tree.filterIsInstance<EtsUiElement>()
        check(elements.any { (it.call.callee as? EtsReference)?.symbol?.name == "Stack" })
        check(elements.count { (it.call.callee as? EtsReference)?.symbol?.name == "Text" } == 8)
        check(elements.count { (it.call.callee as? EtsReference)?.symbol?.name == "Image" } == 2)
        check(elements.count { (it.call.callee as? EtsReference)?.symbol?.name == "TextInput" } == 2)
        val nativeButton = elements.single { (it.call.callee as? EtsReference)?.symbol?.name == "Button" }
        check(nativeButton.children?.single() is EtsUiElement)
        check(nativeButton.attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }.arguments.single() == button.onClick)
        check(elements.filter { (it.call.callee as? EtsReference)?.symbol?.name == "Text" }
            .any { it.call.arguments.single() == buttonLabel.text.value })
        val nativeFields = elements.filter { (it.call.callee as? EtsReference)?.symbol?.name == "TextInput" }
        check(nativeFields.all { field ->
            (field.call.arguments.single() as EtsObject).fields["text"] == materialField.value &&
                field.attributes.single { (it.callee as EtsReference).symbol.name == "onChange" }
                    .arguments.single() == materialField.onValueChange
        })
        fun modifierLayers(widget: Widget<EtsExpression, SourceSpan>): List<EtsUiElement> {
            val result = mutableListOf<EtsUiElement>()
            var current = HarmonyWidgetBackend().lower(widget)
            repeat(widget.modifiers.size) {
                result += current
                current = current.children!!.single() as EtsUiElement
            }
            return result
        }
        fun attributes(element: EtsUiElement) = element.attributes.map { (it.callee as EtsReference).symbol.name }
        val textLayers = modifierLayers(styledText)
        check(textLayers.map(::attributes) == listOf(listOf("width", "height"), listOf("backgroundColor"),
            listOf("enabled", "onClick"), listOf("padding")))
        check(textLayers[2].attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }
            .arguments.single() == styledClick.onClick)
        val imageLayers = modifierLayers(resourceImage)
        check(imageLayers.map(::attributes) == listOf(listOf("enabled", "onClick"),
            listOf("backgroundColor"), listOf("width", "height")))
        check(imageLayers[0].attributes.single { (it.callee as EtsReference).symbol.name == "onClick" }
            .arguments.single() == imageClick.onClick)
        val expected = linkedMapOf(
            "UnknownWidget" to "Unsupported resolved widget API", "UnknownModifier" to "Unsupported resolved widget Modifier API",
            "UnknownArgument" to "widget argument: fontSize", "Conditional" to "Unsupported widget children statement",
            "Helper" to "Unsupported resolved widget API", "EffectfulValue" to "stable scalars",
            "CallbackFactory" to "callback requires a lambda", "NegativePadding" to "finite and non-negative",
            "MutableLocal" to "Mutable widget local", "EarlyReturn" to "Widget return",
            "ArbitraryPainter" to "arbitrary Painter", "RichText" to "requires String text",
            "NonUrlImageModel" to "requires a String URL", "BadImageUrl" to "HTTP(S)",
            "RichTextField" to "rich text values", "DecorationTextField" to "widget argument: decorationBox",
            "MaterialDecoration" to "widget argument: label",
            "TextFieldCallbackFactory" to "requires a lambda",
            "BrushBackground" to "widget argument: brush",
            "ShapedBackground" to "widget argument: shape",
            "ClickSemantics" to "widget argument: onClickLabel",
            "ClickFactory" to "clickable onClick requires a lambda",
            "NegativeSize" to "finite and non-negative",
            "EffectfulBackground" to "stable scalars",
            "UnknownStringToken" to "Unmapped project widget token widgetsnegative.UnknownTokens.label",
            "UnknownColorToken" to "Unmapped project widget token widgetsnegative.UnknownTokens.color")
        val diagnostics = expected.map { (name, message) ->
            val function = functions.single { it.name.asString() == name }
            val failure = try { adapter.lower(function); error("Accepted unsupported fixture $name") } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/Unsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
        println("PASS resolved Compose -> neutral structure -> typed ETS; ${expected.size} source-linked rejections")
    }
}
