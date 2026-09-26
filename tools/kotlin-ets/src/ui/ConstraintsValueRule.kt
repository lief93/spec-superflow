@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*

private val constraintsSource = SourceSpan("EtsBoxConstraints.kt", 0, 0)
internal val boxConstraintsType = etsClassSymbol("__etsBoxConstraints", constraintsSource).type as EtsNamedType
internal val boxConstraintsBindingType = EtsNamedType("Binding", listOf(boxConstraintsType), external = true)
internal data class ConstraintContent(val builder: EtsExpression, val data: EtsExpression)
internal val boxConstraintsArgsType = etsClassSymbol("__etsConstraintArgs", constraintsSource).type as EtsNamedType
internal fun boxConstraintsOptions(data: EtsType) = EtsRecordType("BoxConstraintsOptions", mapOf(
    "content" to wrappedBuilderType(listOf(boxConstraintsArgsType)),
    "data" to data, "alignment" to EtsNamedType("Alignment"),
    "fixedWidth" to EtsTypes.BOOLEAN, "fixedHeight" to EtsTypes.BOOLEAN))

internal class ComposeConstraintsValueRule : CallRule {
    private fun required(program: EtsProgram): Boolean {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id == "compose:boxConstraints") used = true
        } } }
        return used
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> = if (!required(program)) emptyList() else listOf(
        "FrameNode", "BuilderNode", "NodeController", "UIContext", "LayoutConstraint").map {
        EtsImport("@kit.ArkUI", it, "__ets$it")
    } + listOf(EtsImport("@kit.ArkUI", "Binding"), EtsImport("@kit.ArkUI", "UIUtils"))

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        if (!required(program)) return emptyList()
        val parameters = listOf("minWidth", "minHeight", "maxWidth", "maxHeight").map {
            EtsParameter(EtsSymbol("constraints:$it", it, EtsTypes.NUMBER, constraintsSource))
        }
        val receiver = EtsReference(EtsSymbol("constraints:this", "this", boxConstraintsType, constraintsSource, external = true))
        val fields = parameters.map { EtsField(it.symbol.copy(id = "constraints:field:${it.symbol.name}"), readonly = true) }
        val constructor = EtsFunction("constructor", parameters, EtsTypes.VOID, parameters.map {
            EtsExpressionStatement(EtsAssignment(EtsMember(receiver, it.symbol.name, EtsTypes.NUMBER, constraintsSource),
                EtsReference(it.symbol), constraintsSource))
        }, constraintsSource, kind = EtsFunctionKind.CONSTRUCTOR)
        val argsParameters = listOf("bounds" to boxConstraintsBindingType, "data" to EtsTypes.OBJECT,
            "alignment" to EtsNamedType("Alignment")).map { (name, type) ->
            EtsParameter(EtsSymbol("constraints:args:$name", name, type, constraintsSource))
        }
        val argsReceiver = EtsReference(EtsSymbol("constraints:args:this", "this", boxConstraintsArgsType, constraintsSource, external = true))
        val argsConstructor = EtsFunction("constructor", argsParameters, EtsTypes.VOID, argsParameters.map {
            EtsExpressionStatement(EtsAssignment(EtsMember(argsReceiver, it.symbol.name, it.symbol.type, constraintsSource),
                EtsReference(it.symbol), constraintsSource))
        }, constraintsSource, kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(constraintsSource.file!!, listOf(
            EtsClass(boxConstraintsType.name, fields + constructor, constraintsSource, exported = true),
            EtsClass(boxConstraintsArgsType.name, argsParameters.map { EtsField(it.symbol, readonly = true) } + argsConstructor,
                constraintsSource, exported = true))))
    }

    override fun mapType(type: IrType, language: Language): EtsType? =
        if (type.classOrNull?.owner?.let(::symbolName) == "androidx.compose.foundation.layout.BoxWithConstraintsScope") boxConstraintsBindingType else null

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val property = call.symbol.owner.correspondingPropertySymbol?.owner ?: return null
        val name = symbolName(property)
        if (name !in setOf("minWidth", "minHeight", "maxWidth", "maxHeight").map {
                "androidx.compose.foundation.layout.BoxWithConstraintsScope.$it" }) return null
        val receiver = call.dispatchReceiver ?: return null
        val at = language.source(call)
        return EtsMember(EtsMember(language.expression(receiver, scope), "value", boxConstraintsType, at),
            property.name.asString(), EtsTypes.NUMBER, at)
    }
}

internal fun isConstraintDimensionRead(value: IrExpression, scope: Scope): Boolean {
    if (value is IrGetValue) return scope.aliases[value.symbol]?.let { isConstraintDimensionRead(it, scope) } == true
    val call = value as? IrCall ?: return false
    val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName) ?: return false
    return if (property == "androidx.compose.ui.unit.Dp.value")
        call.dispatchReceiver?.let { isConstraintDimensionRead(it, scope) } == true
    else (call.dispatchReceiver as? IrGetValue)?.symbol in scope.bindings &&
        property in setOf("minWidth", "minHeight", "maxWidth", "maxHeight").map {
            "androidx.compose.foundation.layout.BoxWithConstraintsScope.$it"
        }
}
