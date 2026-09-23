@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.architecturefixture

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall

class ArchitectureStateAdapter : AdapterModule {
    override val id = "fixture.architecture-state"
    override val projectCalls = listOf(AdapterProjectCall(
        source = AdapterCallIdentity(
            symbol = "androidx.hilt.navigation.compose.hiltViewModel",
            typeParameters = 1,
            parameters = listOf("androidx.lifecycle.ViewModelStoreOwner", "kotlin.String?"),
            returnType = "VM of androidx.hilt.navigation.compose.hiltViewModel",
        ),
        resolvedSourceReturnType =
            "com.example.android.architecture.blueprints.todoapp.statistics.StatisticsViewModel",
        targetReturnType = EtsNamedType("StatisticsViewModel"),
    ))
    override val targetValues = listOf(AdapterTargetValue(
        "fixture.architecture-state.value", "providedStatisticsViewModel", EtsNamedType("StatisticsViewModel")))
    override val imports = listOf(EtsImport("./ArchitectureInjectionHost", "providedStatisticsViewModel"))

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? =
            target.value("fixture.architecture-state.value", language.type(call.type), language.source(call))
    }
}
