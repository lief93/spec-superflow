@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.render
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid

enum class CoreProfileCategory(val jsonName: String) {
    LANGUAGE("language"),
    STDLIB("stdlib"),
    COMPOSE("compose"),
    PLATFORM("platform"),
    PROJECT_DEPENDENCY("project_dependency"),
}

data class CoreProfileArgumentResolution(val parameter: String, val resolution: String)

data class CoreProfileCall(
    val category: CoreProfileCategory,
    val resolvedSymbol: String,
    val expectedTargetType: String,
    val source: SourceSpan,
    val argumentResolutions: List<CoreProfileArgumentResolution>,
)

data class CoreProfileReport(val calls: List<CoreProfileCall>)

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

private fun profileCategory(call: IrCall): CoreProfileCategory {
    val owner = call.symbol.owner
    if (sourceFile(owner) != null) return CoreProfileCategory.LANGUAGE
    val name = symbolName(owner)
    return when {
        name.startsWith("androidx.compose.") -> CoreProfileCategory.COMPOSE
        name.startsWith("kotlin.") -> CoreProfileCategory.STDLIB
        name.startsWith("java.") || name.startsWith("javax.") || name.startsWith("android.") ||
            name.startsWith("androidx.") || name.startsWith("kotlinx.") || name.startsWith("coil.") ||
            name.startsWith("ohos.") -> CoreProfileCategory.PLATFORM
        else -> CoreProfileCategory.PROJECT_DEPENDENCY
    }
}

fun coreProfilePreflight(module: IrModuleFragment, language: Language, diagnostics: DiagnosticSink): CoreProfileReport {
    val calls = mutableListOf<CoreProfileCall>()
    module.files.forEach { file ->
        diagnostics.currentFile = file.fileEntry.name
        file.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element !is IrCall) {
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
                val expected = try {
                    profileType(language.type(expression.type))
                } catch (_: Unsupported) {
                    "unsupported(" + expression.type.render() + ")"
                }
                calls += CoreProfileCall(profileCategory(expression), symbol, expected, at, resolutions)
                expression.acceptChildrenVoid(this)
            }
        })
    }
    return CoreProfileReport(calls.sortedWith(compareBy({ it.source.file }, { it.source.start }, { it.resolvedSymbol })))
}

internal fun coreProfileJson(report: CoreProfileReport): String {
    fun resolution(value: CoreProfileArgumentResolution) = "{\"parameter\":" + quote(value.parameter) +
        ",\"resolution\":" + quote(value.resolution) + "}"
    fun call(value: CoreProfileCall) = "{\"category\":" + quote(value.category.jsonName) +
        ",\"resolvedSymbol\":" + quote(value.resolvedSymbol) +
        ",\"expectedTargetType\":" + quote(value.expectedTargetType) +
        ",\"source\":" + diagnosticSourceJson(value.source) +
        ",\"argumentResolutions\":[" + value.argumentResolutions.joinToString(",", transform = ::resolution) + "]}"
    val counts = CoreProfileCategory.entries.joinToString(",") { category ->
        quote(category.jsonName) + ":" + report.calls.count { it.category == category }
    }
    return "{\"schemaVersion\":1,\"counts\":{" + counts + "},\"calls\":[\n" +
        report.calls.joinToString(",\n", transform = ::call) + "\n]}\n"
}
