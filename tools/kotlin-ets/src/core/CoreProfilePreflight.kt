@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrField
import org.jetbrains.kotlin.ir.declarations.IrFunction
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.declarations.IrValueDeclaration
import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classFqName
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.hasAnnotation
import org.jetbrains.kotlin.ir.util.render
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.name.FqName

enum class CoreProfileCategory(val jsonName: String, val responsibleModule: String) {
    LANGUAGE("language_semantics", "tools/kotlin-ets/src/language/LanguageLowering.kt"),
    STDLIB("standard_library", "tools/kotlin-ets/src/stdlib/StandardLibraryRules.kt"),
    COMPOSE_WIDGET("neutral_compose_widget", "tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt"),
    MODIFIER("modifier", "tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt"),
    RESOURCES("resources", "tools/kotlin-ets/src/ui/compose/ComposeWidgetAdapter.kt"),
    PROJECT_DEPENDENCY("project_dependencies", "tools/kotlin-ets/src/adapters/AdapterModules.kt"),
}

private const val CORE_PROFILE_FRONTEND_COMPILER_VERSION = "2.1.20"

data class CoreProfileCompilerEnvironment(
    val projectCompilerVersion: String?,
    val frontendCompilerVersion: String = CORE_PROFILE_FRONTEND_COMPILER_VERSION,
    val compatibilityDecision: String,
)

fun coreProfileCompilerEnvironment(projectCompilerVersion: String?): CoreProfileCompilerEnvironment {
    if (projectCompilerVersion == null) return CoreProfileCompilerEnvironment(null,
        compatibilityDecision = "direct_source_input")
    fun parse(value: String, label: String): List<Int> {
        require(Regex("[0-9]+\\.[0-9]+\\.[0-9]+").matches(value)) {
            "$label must be a stable numeric Kotlin version (major.minor.patch): $value"
        }
        return value.split('.').map(String::toInt)
    }
    val project = parse(projectCompilerVersion, "Project compiler version")
    val frontend = parse(CORE_PROFILE_FRONTEND_COMPILER_VERSION, "ETS frontend compiler version")
    require(project.take(2) == frontend.take(2)) {
        "Incompatible Kotlin compiler line: project $projectCompilerVersion, ETS frontend $CORE_PROFILE_FRONTEND_COMPILER_VERSION; " +
            "the project major/minor must match the frontend"
    }
    require(project[2] <= frontend[2]) {
        "Incompatible newer Kotlin patch: project $projectCompilerVersion, ETS frontend $CORE_PROFILE_FRONTEND_COMPILER_VERSION"
    }
    val decision = if (project[2] == frontend[2]) "exact_frontend_version" else "same_language_line_older_patch"
    return CoreProfileCompilerEnvironment(projectCompilerVersion, compatibilityDecision = decision)
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
    val compilerEnvironment: CoreProfileCompilerEnvironment,
    val pageEntries: List<String> = emptyList(),
    val unsupportedNodes: List<CoreProfileUnsupportedNode> = emptyList(),
    val firstUnsupportedNode: CoreProfileUnsupportedNode? = null,
    internal val recognizedNodes: List<CoreProfileNode> = emptyList(),
) {
    /**
     * Preflight type probing is intentionally conservative: framework state and project adapters may own a
     * source value whose target type does not exist until lowering. Once a validated target program exists,
     * source-linked target nodes are stronger evidence than that speculative probe. Only speculative call
     * failures are cleared; explicit degradations and failures recorded by [record] remain reportable.
     */
    fun reconcileGeneratedTarget(program: EtsProgram, degradations: Collection<Diagnostic> = emptyList()): CoreProfileReport {
        val targetSources = linkedMapOf<String, MutableList<Pair<SourceSpan, Boolean>>>()
        program.files.forEach { file ->
            file.declarations.forEach { declaration ->
                walkEts(declaration) { node ->
                    node.source.takeIf { it.file != null && it.start >= 0 && it.end >= it.start }
                        ?.let { targetSources.getOrPut(requireNotNull(it.file)) { mutableListOf() }
                            .add(it to (node is EtsFunction || node is EtsClass)) }
                }
            }
        }
        fun contains(outer: SourceSpan, inner: SourceSpan) = outer.file == inner.file &&
            outer.start >= 0 && inner.start >= outer.start && inner.end <= outer.end
        fun degraded(source: SourceSpan) = degradations.any { degradation ->
            contains(source, degradation.source) || contains(degradation.source, source)
        }
        fun represented(source: SourceSpan, allowBroadContainers: Boolean = false) =
            targetSources[source.file].orEmpty().any { (target, broadContainer) ->
                contains(source, target) || (allowBroadContainers || !broadContainer) && contains(target, source)
        }
        val reconciled = calls.map { call ->
            val unsupported = call.firstUnsupportedNode
            if (unsupported?.kind in setOf("target_type", "missing_argument") &&
                represented(call.source) && !degraded(call.source)) {
                call.copy(firstUnsupportedNode = null)
            } else call
        }
        val reconciledUnsupported = unsupportedNodes.filterNot { unsupported ->
            unsupported.kind in setOf("declared_type", "return_type", "super_type") &&
                represented(unsupported.source, allowBroadContainers = true) && !degraded(unsupported.source)
        }
        return copy(calls = reconciled, unsupportedNodes = reconciledUnsupported,
            firstUnsupportedNode = reconciled.firstNotNullOfOrNull { it.firstUnsupportedNode })
    }

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
        val kind = when {
            failure.code == "PROJECT_ADAPTER_MISSING" ||
                (owner?.category == CoreProfileCategory.PROJECT_DEPENDENCY &&
                    "declared typed adapter" in failure.message) -> "project_adapter_missing"
            failure.code == "PROJECT_ADAPTER_VOID_RESULT" -> "project_adapter_void_result"
            failure.code == "PROJECT_ADAPTER_RETURN_TYPE" -> "project_adapter_return_type"
            failure.code == "PROJECT_ADAPTER_ARGUMENTS" -> "project_adapter_arguments"
            failure.code == "PROJECT_ADAPTER_SCOPE" -> "project_adapter_scope"
            node?.kind in setOf("typed_call", "resolved_call") -> "unsupported_call"
            node?.kind == "resolved_field" -> "unsupported_field"
            node?.kind == "resolved_object" -> "unsupported_object"
            else -> "unsupported_expression"
        }
        val unsupported = CoreProfileUnsupportedNode(kind,
            node?.symbol, failure.message, failure.source, module)
        return copy(calls = calls.map { call ->
            if (call === owner && call.firstUnsupportedNode == null) call.copy(firstUnsupportedNode = unsupported) else call
        }, unsupportedNodes = if (unsupportedNodes.any { it == unsupported }) unsupportedNodes else unsupportedNodes + unsupported,
            firstUnsupportedNode = firstUnsupportedNode ?: unsupported)
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
    "androidx.compose.ui.res.pluralStringResource",
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
    "androidx.compose.ui.res.stringResource", "androidx.compose.ui.res.pluralStringResource" -> "tools/kotlin-ets/src/ui/StringResources.kt"
    "androidx.compose.ui.res.painterResource" -> "tools/kotlin-ets/src/ui/ImageResources.kt"
    else -> category.responsibleModule
}

fun coreProfilePreflight(module: IrModuleFragment, language: Language, diagnostics: DiagnosticSink,
    compilerEnvironment: CoreProfileCompilerEnvironment = coreProfileCompilerEnvironment(null)): CoreProfileReport {
    val calls = mutableListOf<CoreProfileCall>()
    val recognizedNodes = mutableListOf<CoreProfileNode>()
    val unsupportedNodes = linkedMapOf<String, CoreProfileUnsupportedNode>()
    val pageEntries = linkedSetOf<String>()
    val preview = FqName("androidx.compose.ui.tooling.preview.Preview")
    val composable = FqName("androidx.compose.runtime.Composable")
    module.files.forEach { file ->
        diagnostics.currentFile = file.fileEntry.name
        val sourceAnchors = mutableListOf<SourceSpan>()
        file.acceptChildrenVoid(object : IrElementVisitorVoid {
            private fun frameworkLambdaReceiver(value: IrValueDeclaration): Boolean {
                val parameter = value as? IrValueParameter ?: return false
                val owner = parameter.parent as? IrFunction ?: return false
                return owner.name.isSpecial && owner.extensionReceiverParameter === parameter &&
                    parameter.type.classFqName?.asString()?.startsWith("androidx.compose.") == true
            }

            private fun inspectType(type: IrType, kind: String, at: SourceSpan) {
                try {
                    language.type(type)
                } catch (failure: Unsupported) {
                    val symbol = type.classFqName?.asString() ?: type.render()
                    val owner = type.classOrNull?.owner
                    val responsible = when {
                        owner != null && sourceFile(owner) != null -> CoreProfileCategory.LANGUAGE.responsibleModule
                        symbol.startsWith("kotlin.") -> CoreProfileCategory.LANGUAGE.responsibleModule
                        symbol.startsWith("androidx.compose.") -> CoreProfileCategory.COMPOSE_WIDGET.responsibleModule
                        else -> CoreProfileCategory.PROJECT_DEPENDENCY.responsibleModule
                    }
                    val unsupported = CoreProfileUnsupportedNode(kind, symbol,
                        failure.diagnostic.message, at, responsible)
                    val key = listOf(kind, symbol, at.file, at.start, at.end).joinToString(":")
                    unsupportedNodes.putIfAbsent(key, unsupported)
                }
            }

            override fun visitElement(element: IrElement) {
                if (element is IrSimpleFunction && sourceFile(element) != null &&
                    element.hasAnnotation(preview) && element.hasAnnotation(composable)) {
                    pageEntries += symbolName(element)
                }
                val elementSource = sourceSpan(element, diagnostics)
                val sourceLinked = elementSource.start >= 0 && elementSource.end >= elementSource.start
                if (sourceLinked) sourceAnchors += elementSource
                val at = if (sourceLinked) elementSource else sourceAnchors.lastOrNull() ?: elementSource
                try {
                    when (element) {
                        is IrValueDeclaration -> if (!frameworkLambdaReceiver(element))
                            inspectType(element.type, "declared_type", at)
                        is IrField -> inspectType(element.type, "declared_type", at)
                        is IrSimpleFunction -> inspectType(element.returnType, "return_type", at)
                        is IrClass -> element.superTypes.forEach { inspectType(it, "super_type", at) }
                    }
                    if (element !is IrCall) {
                        val node = when (element) {
                            is IrGetField -> CoreProfileNode("resolved_field", symbolName(element.symbol.owner), at)
                            is IrGetObjectValue -> CoreProfileNode("resolved_object", symbolName(element.symbol.owner), at)
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
                    val category = profileCategory(expression)
                    val module = responsibleModule(expression, category)
                    var unsupported: CoreProfileUnsupportedNode? = null
                    val resolutions = owner.valueParameters.mapIndexedNotNull { index, parameter ->
                        if (expression.getValueArgument(index) != null) null
                        else when {
                            parameter.defaultValue != null -> CoreProfileArgumentResolution(parameter.name.asString(), "source_default")
                            parameter.varargElementType != null -> CoreProfileArgumentResolution(parameter.name.asString(), "empty_vararg")
                            else -> language.callRules.firstNotNullOfOrNull {
                                it.omittedArgumentResolution(expression, parameter)
                            }?.let { CoreProfileArgumentResolution(parameter.name.asString(), it) }
                                ?: run {
                                    unsupported = unsupported ?: CoreProfileUnsupportedNode(
                                        "missing_argument", symbolName(owner),
                                        "Preflight found a missing resolved argument ${parameter.name} in ${symbolName(owner)}",
                                        at, module)
                                    null
                                }
                        }
                    }
                    val expected = try {
                        profileType(language.type(expression.type))
                    } catch (failure: Unsupported) {
                        val source = failure.diagnostic.source.takeIf { it.start >= 0 && it.end >= it.start } ?: at
                        unsupported = unsupported ?: CoreProfileUnsupportedNode("target_type", symbolName(owner),
                            failure.diagnostic.message, source, module)
                        null
                    }
                    val recognizedKind = if (expected == null) "resolved_call" else "typed_call"
                    val recognized = CoreProfileNode(recognizedKind, symbolName(owner), at)
                    recognizedNodes += recognized
                    calls += CoreProfileCall(category, symbol, expected, at, resolutions, recognized, unsupported, module)
                    expression.acceptChildrenVoid(this)
                } finally {
                    if (sourceLinked) sourceAnchors.removeAt(sourceAnchors.lastIndex)
                }
            }
        })
    }
    val sorted = calls.sortedWith(compareBy({ it.source.file }, { it.source.start }, { it.resolvedSymbol }))
    val sortedUnsupported = unsupportedNodes.values.sortedWith(compareBy({ it.source.file }, { it.source.start }, { it.symbol }))
    return CoreProfileReport(sorted, compilerEnvironment, pageEntries.sorted(), sortedUnsupported,
        sorted.firstNotNullOfOrNull { it.firstUnsupportedNode }, recognizedNodes)
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
    return "{\"schemaVersion\":2,\"projectCompilerVersion\":" +
        (report.compilerEnvironment.projectCompilerVersion?.let(::quote) ?: "null") +
        ",\"frontendCompilerVersion\":" + quote(report.compilerEnvironment.frontendCompilerVersion) +
        ",\"compatibilityDecision\":" + quote(report.compilerEnvironment.compatibilityDecision) +
        ",\"pageEntries\":[" + report.pageEntries.joinToString(",", transform = ::quote) + "]" +
        ",\"unsupportedNodes\":[" + report.unsupportedNodes.joinToString(",", transform = ::unsupported) + "]" +
        ",\"counts\":{" + counts + "},\"coverage\":{" + coverage + "}" +
        ",\"firstUnsupportedNode\":" + (report.firstUnsupportedNode?.let(::unsupported) ?: "null") +
        ",\"calls\":[\n" + report.calls.joinToString(",\n", transform = ::call) + "\n]}\n"
}
