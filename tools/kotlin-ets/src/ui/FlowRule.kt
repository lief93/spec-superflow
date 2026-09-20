@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.types.*

private val flowSource = SourceSpan("EtsFlow.kt", -1, -1)
private val flowClass = etsClassSymbol("EtsFlow", flowSource)
private val flowTypeParameter = EtsTypeParameter("compose:flow:T", "T")
private val flowNames = setOf(
    "kotlinx.coroutines.flow.Flow",
    "kotlinx.coroutines.flow.SharedFlow",
    "kotlinx.coroutines.flow.StateFlow",
    "kotlinx.coroutines.flow.MutableSharedFlow",
    "kotlinx.coroutines.flow.MutableStateFlow",
)
private val collectionApis = setOf(
    "kotlinx.coroutines.flow.Flow.collect",
    "kotlinx.coroutines.flow.SharedFlow.collect",
    "kotlinx.coroutines.flow.StateFlow.collect",
    "kotlinx.coroutines.flow.collect",
    "androidx.compose.runtime.collectAsState",
    "androidx.lifecycle.compose.collectAsStateWithLifecycle",
    "androidx.compose.runtime.collectAsStateWithLifecycle",
)
private val snapshotProperties = setOf(
    "kotlinx.coroutines.flow.StateFlow.value",
    "kotlinx.coroutines.flow.MutableStateFlow.value",
    "kotlinx.coroutines.flow.SharedFlow.replayCache",
    "kotlinx.coroutines.flow.MutableSharedFlow.replayCache",
)

/** Flow is a typed host value. Live collection is not a remembered snapshot and is refused. */
internal class ComposeFlowRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val owner = type.classOrNull?.owner ?: return null
        if (sourceFile(owner) != null || symbolName(owner) !in flowNames) return null
        val argument = ((type as? IrSimpleType)?.arguments?.singleOrNull() as? IrTypeProjection)?.type
            ?: return EtsNamedType(flowClass.name, listOf(EtsTypes.OBJECT), flowClass.id)
        return EtsNamedType(flowClass.name, listOf(language.type(argument)), flowClass.id)
    }

    override fun lowerConstructor(call: IrConstructorCall, language: Language, scope: Scope): EtsExpression? {
        val parent = call.symbol.owner.parent as? org.jetbrains.kotlin.ir.declarations.IrClass ?: return null
        if (sourceFile(parent) != null || symbolName(parent) !in setOf(
                "kotlinx.coroutines.flow.MutableStateFlow", "kotlinx.coroutines.flow.MutableSharedFlow")) return null
        val at = language.source(call)
        val initial = (0 until call.valueArgumentsCount).mapNotNull { call.getValueArgument(it)?.let { value -> language.expression(value, scope) } }
        val type = language.type(call.type) as EtsNamedType
        return if (initial.isEmpty()) EtsNew(type, emptyList(), at)
        else EtsCall(EtsLambda(emptyList(), initial.map { EtsExpressionStatement(it) } +
            listOf(EtsReturn(EtsNew(type, emptyList(), at), at)), type, at), emptyList(), type, at)
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        if (sourceFile(owner) != null) return null
        val api = symbolName(owner)
        val property = owner.correspondingPropertySymbol?.owner?.let(::symbolName)
        if (api in setOf("kotlinx.coroutines.flow.MutableStateFlow", "kotlinx.coroutines.flow.MutableSharedFlow",
                "kotlinx.coroutines.flow.emptyFlow", "kotlinx.coroutines.flow.flowOf")) {
            val at = language.source(call)
            val type = language.type(call.type) as EtsNamedType
            val arguments = (0 until call.valueArgumentsCount).mapNotNull { index ->
                call.getValueArgument(index)?.let { language.expression(it, scope) }
            }
            return if (arguments.isEmpty()) EtsNew(type, emptyList(), at)
            else EtsCall(EtsLambda(emptyList(), arguments.map { EtsExpressionStatement(it) } +
                listOf(EtsReturn(EtsNew(type, emptyList(), at), at)), type, at), emptyList(), type, at)
        }
        if (api !in collectionApis && !api.endsWith(".collectAsState") && !api.endsWith(".collectAsStateWithLifecycle") &&
            property !in snapshotProperties) return null
        throw Unsupported(Diagnostic("UNSUPPORTED",
            "Flow collection requires a remembered snapshot; live ${property ?: api} is not mapped", language.source(call)))
    }

    override fun targetFiles(program: EtsProgram): List<EtsFile> {
        if (!usesType(program)) return emptyList()
        val constructor = EtsFunction("constructor", emptyList(), EtsTypes.VOID, emptyList(), flowSource,
            kind = EtsFunctionKind.CONSTRUCTOR)
        return listOf(EtsFile(flowSource.file!!, listOf(
            EtsClass(flowClass.name, listOf(constructor), flowSource, exported = true,
                typeParameters = listOf(flowTypeParameter)))))
    }

    private fun usesType(program: EtsProgram): Boolean {
        fun uses(type: EtsType): Boolean = when (type) {
            is EtsNamedType -> type.symbolId == flowClass.id || type.arguments.any(::uses)
            is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
            is EtsNullableType -> uses(type.inner)
            else -> false
        }
        var found = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsExpression && uses(node.type) || node is EtsFunction && uses(node.symbol.type)) found = true
        } } }
        return found
    }
}
