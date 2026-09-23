@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.adapters

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall

/** Hilt owns ViewModel construction; a root default becomes an explicit host-supplied component prop. */
class AndroidxHiltModule : AdapterModule {
    override val id = "androidx.hilt.root-default"
    override val sourceCalls = setOf("androidx.hilt.navigation.compose.hiltViewModel")
    override val rootDefaultCalls = sourceCalls

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            if (symbolName(call.symbol.owner) != "androidx.hilt.navigation.compose.hiltViewModel") return null
            throw Unsupported(Diagnostic("UNSUPPORTED",
                "hiltViewModel is supported only as a direct root @Composable parameter default; supply the required target component prop",
                language.source(call)))
        }
    }
}
