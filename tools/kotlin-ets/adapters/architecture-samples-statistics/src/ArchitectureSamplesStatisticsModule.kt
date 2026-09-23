@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.adapters

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private const val sourcePackage = "com.example.android.architecture.blueprints.todoapp.statistics"
private val bridgeSource = SourceSpan("ArchitectureSamplesStatisticsAdapter.ets", 0, 0)
private val uiStateContract = EtsClass("StatisticsUiState", listOf(
    EtsField(EtsSymbol("architecture-samples:statistics-ui-state:isEmpty", "isEmpty", EtsTypes.BOOLEAN, bridgeSource), readonly = true),
    EtsField(EtsSymbol("architecture-samples:statistics-ui-state:isLoading", "isLoading", EtsTypes.BOOLEAN, bridgeSource), readonly = true),
    EtsField(EtsSymbol("architecture-samples:statistics-ui-state:activeTasksPercent", "activeTasksPercent", EtsTypes.NUMBER, bridgeSource), readonly = true),
    EtsField(EtsSymbol("architecture-samples:statistics-ui-state:completedTasksPercent", "completedTasksPercent", EtsTypes.NUMBER, bridgeSource), readonly = true),
), bridgeSource, exported = true, kind = EtsClassKind.INTERFACE,
    sourceName = "$sourcePackage.StatisticsUiState")
private val uiStateType = EtsNamedType(uiStateContract.name, symbolId = uiStateContract.symbol.id)
private val stateFlowSymbol = etsClassSymbol("EtsStateFlow", SourceSpan("EtsFlow.kt", -1, -1))
private val stateFlowType = EtsNamedType(stateFlowSymbol.name, listOf(uiStateType), symbolId = stateFlowSymbol.id)
private val refreshMethod = EtsFunction("refresh", emptyList(), EtsTypes.VOID, emptyList(), bridgeSource,
    kind = EtsFunctionKind.METHOD, abstract = true)
private val viewModelContract = EtsClass("StatisticsViewModelBridge", listOf(
    EtsField(EtsSymbol("architecture-samples:statistics-view-model:uiState", "uiState", stateFlowType, bridgeSource), readonly = true),
    refreshMethod,
), bridgeSource, exported = true, kind = EtsClassKind.INTERFACE,
    sourceName = "$sourcePackage.StatisticsViewModel")
private val viewModelType = EtsNamedType(viewModelContract.name, symbolId = viewModelContract.symbol.id)

/** Host bridge for the pinned architecture-samples Statistics screen's injected dependency. */
class ArchitectureSamplesStatisticsModule : AdapterModule {
    override val id = "project.architecture-samples.statistics"
    override val replacesSourceBodies = true
    override val sourceTypes = setOf("$sourcePackage.StatisticsViewModel", "$sourcePackage.StatisticsUiState")
    override val sourceCalls = setOf(
        "$sourcePackage.StatisticsViewModel.<get-uiState>",
        "$sourcePackage.StatisticsViewModel.refresh",
        "$sourcePackage.StatisticsUiState.<get-isEmpty>",
        "$sourcePackage.StatisticsUiState.<get-isLoading>",
        "$sourcePackage.StatisticsUiState.<get-activeTasksPercent>",
        "$sourcePackage.StatisticsUiState.<get-completedTasksPercent>",
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun mapType(type: IrType, language: Language): EtsType? = when (type.classOrNull?.owner?.let(::symbolName)) {
            "$sourcePackage.StatisticsViewModel" -> viewModelType
            "$sourcePackage.StatisticsUiState" -> uiStateType
            else -> null
        }

        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            val api = symbolName(call.symbol.owner)
            if (api !in sourceCalls) return null
            if (call.valueArgumentsCount != 0) fail(call, language, "Statistics host bridge calls require no value arguments")
            val receiverSource = call.dispatchReceiver
                ?: fail(call, language, "Statistics host bridge requires a dispatch receiver")
            val receiver = language.expression(receiverSource, scope)
            val source = language.source(call)
            return when (api) {
                "$sourcePackage.StatisticsViewModel.refresh" -> EtsCall(EtsMember(receiver, "refresh",
                    EtsFunctionType(emptyList(), EtsTypes.VOID), source, refreshMethod.symbol.id),
                    emptyList(), EtsTypes.VOID, source)
                else -> {
                    val name = api.substringAfter("<get-").substringBefore('>')
                    EtsMember(receiver, name, language.type(call.type), source,
                        "architecture-samples:${if (api.contains("StatisticsViewModel")) "statistics-view-model" else "statistics-ui-state"}:$name")
                }
            }
        }

        override fun targetFiles(program: EtsProgram): List<EtsFile> =
            listOf(EtsFile(bridgeSource.file!!, listOf(uiStateContract, viewModelContract)))
    }

    private fun fail(call: IrCall, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
}
