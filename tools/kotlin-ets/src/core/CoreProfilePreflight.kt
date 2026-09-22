@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.types.classFqName
import org.jetbrains.kotlin.ir.util.render
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid

enum class CoreProfileCategory(val jsonName: String, val responsibleModule: String) {
    LANGUAGE("language_semantics", "tools/kotlin-ets/src/language/LanguageLowering.kt"),
    STDLIB("standard_library", "tools/kotlin-ets/src/stdlib/StandardLibraryRules.kt"),
    COMPOSE_WIDGET("neutral_compose_widget", "tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt"),
    MODIFIER("modifier", "tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt"),
    RESOURCES("resources", "tools/kotlin-ets/src/ui/ComposeLowering.kt"),
    PROJECT_DEPENDENCY("project_dependencies", "tools/kotlin-ets/src/adapters/AdapterModules.kt"),
}

data class CoreProfileArgumentResolution(val parameter: String, val resolution: String)

data class CoreProfileNode(val kind: String, val symbol: String, val source: SourceSpan)

data class CoreProfileUnsupportedNode(
    val kind: String,
    val symbol: String?,
    val message: String,
    val source: SourceSpan,
    val responsibleModule: String,
)

data class CoreProfileCall(
    val category: CoreProfileCategory,
    val resolvedSymbol: String,
    val expectedTargetType: String?,
    val source: SourceSpan,
    val argumentResolutions: List<CoreProfileArgumentResolution>,
    val finalRecognizedNode: CoreProfileNode,
    val firstUnsupportedNode: CoreProfileUnsupportedNode? = null,
    val responsibleModule: String = category.responsibleModule,
)

data class CoreProfileReport(
    val calls: List<CoreProfileCall>,
    val firstUnsupportedNode: CoreProfileUnsupportedNode? = null,
    internal val recognizedNodes: List<CoreProfileNode> = emptyList(),
) {
    fun record(failure: Diagnostic): CoreProfileReport {
        fun contains(source: SourceSpan) = source.file == failure.source.file && source.start >= 0 &&
            failure.source.start >= source.start && failure.source.end <= source.end
        val candidates = calls.filter { call ->
            contains(call.source)
        }
        val owner = candidates.minByOrNull { it.source.end - it.source.start }
        val node = recognizedNodes.firstOrNull { it.source.file == failure.source.file &&
            it.source.start == failure.source.start && it.source.end == failure.source.end }
        val module = owner?.responsibleModule ?: CoreProfileCategory.LANGUAGE.responsibleModule
        val kind = when (node?.kind) {
            "typed_call", "resolved_call" -> "unsupported_call"
            "resolved_field" -> "unsupported_field"
            "resolved_object" -> "unsupported_object"
            else -> "unsupported_expression"
        }
        val unsupported = CoreProfileUnsupportedNode(kind,
            node?.symbol, failure.message, failure.source, module)
        return copy(calls = calls.map { call ->
            if (call === owner && call.firstUnsupportedNode == null) call.copy(firstUnsupportedNode = unsupported) else call
        }, firstUnsupportedNode = firstUnsupportedNode ?: unsupported)
    }
}

private fun profileType(type: EtsType): String = when (type) {
    is EtsCapturedType -> profileType(type.readType)
    is EtsNamedType -> type.name + if (type.arguments.isEmpty()) "" else
        type.arguments.joinToString(", ", "<", ">", transform = ::profileType)
    is EtsRecordType -> type.name
    is EtsTypeParameterType -> type.name
    is EtsFunctionType -> type.parameters.joinToString(", ", "(", ")") { profileType(it) } +
        " => " + profileType(type.result)
    is EtsNullableType -> profileType(type.inner) + " | null"
    is EtsTupleType -> type.elements.joinToString(", ", "[", "]", transform = ::profileType)
}

private val resourceCalls = setOf(
    "androidx.compose.ui.res.stringResource",
    "androidx.compose.ui.res.painterResource",
    "androidx.compose.ui.res.colorResource",
    "androidx.compose.ui.res.dimensionResource",
    "androidx.compose.ui.res.integerResource",
)

private fun profileCategory(call: IrCall): CoreProfileCategory {
    val owner = call.symbol.owner
    if (sourceFile(owner) != null) return CoreProfileCategory.LANGUAGE
    val name = symbolName(owner)
    val receiverTypes = listOfNotNull(call.dispatchReceiver?.type, call.extensionReceiver?.type, call.type)
        .mapNotNull { it.classFqName?.asString() }
    return when {
        name in resourceCalls || name.startsWith("androidx.compose.ui.res.") -> CoreProfileCategory.RESOURCES
        receiverTypes.any { it == "androidx.compose.ui.Modifier" || it == "androidx.compose.ui.Modifier.Companion" } ->
            CoreProfileCategory.MODIFIER
        name.startsWith("androidx.compose.") || name.startsWith("coil.compose.") -> CoreProfileCategory.COMPOSE_WIDGET
        name.startsWith("kotlin.") -> CoreProfileCategory.STDLIB
        else -> CoreProfileCategory.PROJECT_DEPENDENCY
    }
}

private fun responsibleModule(call: IrCall, category: CoreProfileCategory): String = when (symbolName(call.symbol.owner)) {
    "androidx.compose.ui.res.stringResource" -> "tools/kotlin-ets/src/ui/StringResources.kt"
    "androidx.compose.ui.res.painterResource" -> "tools/kotlin-ets/src/ui/ImageResources.kt"
    else -> category.responsibleModule
}

fun coreProfilePreflight(module: IrModuleFragment, language: Language, diagnostics: DiagnosticSink): CoreProfileReport {
    val calls = mutableListOf<CoreProfileCall>()
    val recognizedNodes = mutableListOf<CoreProfileNode>()
    module.files.forEach { file ->
        diagnostics.currentFile = file.fileEntry.name
        file.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element !is IrCall) {
                    val node = when (element) {
                        is IrGetField -> CoreProfileNode("resolved_field", symbolName(element.symbol.owner),
                            sourceSpan(element, diagnostics))
                        is IrGetObjectValue -> CoreProfileNode("resolved_object", symbolName(element.symbol.owner),
                            sourceSpan(element, diagnostics))
                        else -> null
                    }
                    if (node != null) recognizedNodes += node
                    element.acceptChildrenVoid(this)
                    return
                }
                val expression = element
                val owner = expression.symbol.owner
                val symbol = symbolName(owner) + owner.valueParameters.joinToString(",", "(", ")") { it.type.render() } +
                    ":" + owner.returnType.render()
                val at = sourceSpan(expression, diagnostics)
                val resolutions = owner.valueParameters.mapIndexedNotNull { index, parameter ->
                    if (expression.getValueArgument(index) != null) null
                    else when {
                        parameter.defaultValue != null -> CoreProfileArgumentResolution(parameter.name.asString(), "source_default")
                        parameter.varargElementType != null -> CoreProfileArgumentResolution(parameter.name.asString(), "empty_vararg")
                        else -> diagnostics.unsupported(expression,
                            "Preflight found a missing resolved argument ${parameter.name} in ${symbolName(owner)}")
                    }
                }
                val category = profileCategory(expression)
                val module = responsibleModule(expression, category)
                var unsupported: CoreProfileUnsupportedNode? = null
                val expected = try {
                    profileType(language.type(expression.type))
                } catch (failure: Unsupported) {
                    unsupported = CoreProfileUnsupportedNode("target_type", symbolName(owner), failure.diagnostic.message,
                        failure.diagnostic.source, module)
                    null
                }
                val recognizedKind = if (expected == null) "resolved_call" else "typed_call"
                val recognized = CoreProfileNode(recognizedKind, symbolName(owner), at)
                recognizedNodes += recognized
                calls += CoreProfileCall(category, symbol, expected, at, resolutions, recognized, unsupported, module)
                expression.acceptChildrenVoid(this)
            }
        })
    }
    val sorted = calls.sortedWith(compareBy({ it.source.file }, { it.source.start }, { it.resolvedSymbol }))
    return CoreProfileReport(sorted, sorted.firstNotNullOfOrNull { it.firstUnsupportedNode }, recognizedNodes)
}

internal fun coreProfileJson(report: CoreProfileReport): String {
    fun resolution(value: CoreProfileArgumentResolution) = "{\"parameter\":" + quote(value.parameter) +
        ",\"resolution\":" + quote(value.resolution) + "}"
    fun node(value: CoreProfileNode) = "{\"kind\":" + quote(value.kind) +
        ",\"symbol\":" + quote(value.symbol) + ",\"source\":" + diagnosticSourceJson(value.source) + "}"
    fun unsupported(value: CoreProfileUnsupportedNode) = "{\"kind\":" + quote(value.kind) +
        ",\"symbol\":" + (value.symbol?.let(::quote) ?: "null") +
        ",\"message\":" + quote(value.message) + ",\"source\":" + diagnosticSourceJson(value.source) +
        ",\"responsibleModule\":" + quote(value.responsibleModule) + "}"
    fun call(value: CoreProfileCall) = "{\"category\":" + quote(value.category.jsonName) +
        ",\"resolvedSymbol\":" + quote(value.resolvedSymbol) +
        ",\"expectedTargetType\":" + (value.expectedTargetType?.let(::quote) ?: "null") +
        ",\"source\":" + diagnosticSourceJson(value.source) +
        ",\"argumentResolutions\":[" + value.argumentResolutions.joinToString(",", transform = ::resolution) + "]" +
        ",\"finalRecognizedNode\":" + node(value.finalRecognizedNode) +
        ",\"firstUnsupportedNode\":" + (value.firstUnsupportedNode?.let(::unsupported) ?: "null") +
        ",\"responsibleModule\":" + quote(value.responsibleModule) + "}"
    val counts = CoreProfileCategory.entries.joinToString(",") { category ->
        quote(category.jsonName) + ":" + report.calls.count { it.category == category }
    }
    val coverage = CoreProfileCategory.entries.joinToString(",") { category ->
        val values = report.calls.filter { it.category == category }
        val recognized = values.count { it.firstUnsupportedNode == null }
        val percentage = if (values.isEmpty()) "null" else ((recognized * 10000 / values.size) / 100.0).toString()
        quote(category.jsonName) + ":{\"total\":" + values.size + ",\"recognized\":" + recognized +
            ",\"unsupported\":" + (values.size - recognized) + ",\"percentage\":" + percentage + "}"
    }
    return "{\"schemaVersion\":2,\"counts\":{" + counts + "},\"coverage\":{" + coverage + "}" +
        ",\"firstUnsupportedNode\":" + (report.firstUnsupportedNode?.let(::unsupported) ?: "null") +
        ",\"calls\":[\n" + report.calls.joinToString(",\n", transform = ::call) + "\n]}\n"
}
