@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.adapters

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.classOrNull

private val refreshOptionsType = EtsRecordType("RefreshOptions", mapOf("refreshing" to EtsTypes.BOOLEAN))
private val refreshCallbackType = EtsFunctionType(emptyList(), EtsTypes.VOID)

/** Maps Accompanist's bounded pull-to-refresh contract to the native ArkUI Refresh control. */
class AccompanistSwipeRefreshModule : AdapterModule {
    override val id = "accompanist.swipe-refresh"
    override val sourceCalls = setOf(
        "com.google.accompanist.swiperefresh.SwipeRefresh",
        "com.google.accompanist.swiperefresh.rememberSwipeRefreshState",
    )
    override val sourceTypes = setOf("com.google.accompanist.swiperefresh.SwipeRefreshState")
    override val targetCalls = listOf(
        AdapterTargetCall("accompanist.swipe-refresh.control", "Refresh",
            EtsFunctionType(listOf(refreshOptionsType), EtsTypes.VOID)),
        AdapterTargetCall("accompanist.swipe-refresh.on-refreshing", "onRefreshing",
            EtsFunctionType(listOf(refreshCallbackType), EtsTypes.VOID)),
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun mapType(type: org.jetbrains.kotlin.ir.types.IrType, language: Language): EtsType? =
            if (type.classOrNull?.owner?.let(::symbolName) in sourceTypes) EtsTypes.BOOLEAN else null

        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            if (symbolName(call.symbol.owner) != "com.google.accompanist.swiperefresh.rememberSwipeRefreshState") return null
            val parameters = call.symbol.owner.valueParameters
            if (parameters.map { it.name.asString() } != listOf("isRefreshing"))
                fail(call, language, "rememberSwipeRefreshState requires exactly one isRefreshing value")
            val value = argument(call, "isRefreshing")
                ?: fail(call, language, "rememberSwipeRefreshState requires isRefreshing")
            return language.expression(value, scope).also {
                if (it.type != EtsTypes.BOOLEAN)
                    fail(call, language, "rememberSwipeRefreshState requires a Boolean isRefreshing value")
            }
        }

        override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
            if (ui == null || symbolName(call.symbol.owner) != "com.google.accompanist.swiperefresh.SwipeRefresh") return null
            val supported = setOf("state", "onRefresh", "modifier", "content")
            call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
                if (call.getValueArgument(index) != null && parameter.name.asString() !in supported)
                    fail(call, language, "Unsupported SwipeRefresh argument: ${parameter.name}")
            }
            val stateSource = argument(call, "state") ?: fail(call, language, "SwipeRefresh requires state")
            val state = language.expression(stateSource, scope)
            if (state.type != EtsTypes.BOOLEAN) fail(call, language, "SwipeRefresh requires mapped SwipeRefreshState")
            val callbackSource = argument(call, "onRefresh") ?: fail(call, language, "SwipeRefresh requires onRefresh")
            val callback = language.expression(callbackSource, scope)
            if (!etsAssignable(callback.type, refreshCallbackType))
                fail(call, language, "SwipeRefresh requires a non-null () -> Unit onRefresh callback")
            val content = argument(call, "content") ?: fail(call, language, "SwipeRefresh requires content")
            val source = language.source(call)
            val options = EtsObject(linkedMapOf("refreshing" to state), refreshOptionsType, source)
            val control = EtsUiElement(target.call("accompanist.swipe-refresh.control", listOf(options), source),
                ui.content(content, scope),
                listOf(target.call("accompanist.swipe-refresh.on-refreshing", listOf(callback), source)))
            return ui.decorate(argument(call, "modifier"), scope, control)
        }
    }

    private fun fail(call: IrCall, language: Language, message: String): Nothing =
        throw Unsupported(Diagnostic("UNSUPPORTED", message, language.source(call)))
}
