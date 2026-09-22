@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.compose

import dev.ets.*
import java.util.Collections
import java.util.IdentityHashMap
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.IrStatement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.symbols.IrSimpleFunctionSymbol
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.isBoolean
import org.jetbrains.kotlin.ir.types.isInt
import org.jetbrains.kotlin.ir.types.isString

/** Extracts the small Compose state profile before neutral widget adaptation. */
class ComposeStateLowering(private val language: Language, private val diagnostics: DiagnosticSink) {
    data class Plan(
        val fields: List<EtsField>,
        val scope: Scope,
        val handledStatements: Set<IrStatement>,
        val pagers: Map<IrValueSymbol, PagerStateBinding> = emptyMap(),
        val scrolls: Map<IrValueSymbol, ScrollStateBinding> = emptyMap(),
        val lazyLists: Map<IrValueSymbol, LazyListStateBinding> = emptyMap(),
    )

    data class PagerStateBinding(
        val currentPage: EtsExpression,
        val pageCount: EtsExpression,
        val controller: EtsExpression,
    )

    data class ScrollStateBinding(val offset: EtsExpression)

    data class LazyListStateBinding(
        val initialIndex: EtsExpression,
        val initialOffset: EtsExpression,
        val firstVisibleIndex: EtsExpression,
        val controller: EtsExpression,
        val initialOffsetApplied: EtsExpression?,
        val source: SourceSpan,
    )

    private data class State(
        val field: EtsField,
        val holder: IrValueSymbol,
        val getter: IrSimpleFunctionSymbol? = null,
        val setter: IrSimpleFunctionSymbol? = null,
    )

    private data class PagerState(
        val holder: IrValueSymbol,
        val currentPage: EtsField,
        val pageCount: EtsExpression,
        val controller: EtsField,
    )

    private data class ScrollState(val holder: IrValueSymbol, val offset: EtsField)

    private data class LazyListState(
        val holder: IrValueSymbol,
        val initialIndex: EtsExpression,
        val initialOffset: EtsExpression,
        val firstVisibleIndex: EtsField,
        val controller: EtsField,
        val initialOffsetApplied: EtsField?,
        val source: SourceSpan,
    )

    fun lower(function: IrSimpleFunction, scope: Scope, componentName: String): Plan {
        diagnostics.currentFile = sourceFile(function)?.fileEntry?.name
        val statements = when (val body = function.body) {
            is IrBlockBody -> body.statements
            is IrExpressionBody -> listOf(body.expression)
            null -> diagnostics.unsupported(function, "Widget entry has no body")
            else -> diagnostics.unsupported(body, "Unsupported widget body")
        }
        val componentType = etsClassSymbol(componentName, language.source(function)).type
        val self = EtsReference(EtsSymbol("compose-state:${language.source(function).file}:${language.source(function).start}:this",
            "this", componentType, language.source(function), external = true))
        val handled = Collections.newSetFromMap(IdentityHashMap<IrStatement, Boolean>())
        val states = mutableListOf<State>()
        val pagerStates = mutableListOf<PagerState>()
        val scrollStates = mutableListOf<ScrollState>()
        val lazyListStates = mutableListOf<LazyListState>()
        val fields = mutableListOf<EtsField>()
        statements.forEach { statement ->
            val state = state(statement, scope, handled)
            if (state != null) {
                states += state
                fields += state.field
            } else {
                val pager = pagerState(statement, handled)
                if (pager != null) {
                    pagerStates += pager
                    fields += listOf(pager.currentPage, pager.controller)
                } else {
                    val scroll = scrollState(statement, handled)
                    if (scroll != null) {
                        scrollStates += scroll
                        fields += scroll.offset
                    } else lazyListState(statement, handled)?.let { lazy ->
                        lazyListStates += lazy
                        fields += listOfNotNull(lazy.firstVisibleIndex, lazy.controller,
                            lazy.initialOffsetApplied)
                    }
                }
            }
        }
        if (states.isEmpty() && pagerStates.isEmpty() && scrollStates.isEmpty() && lazyListStates.isEmpty())
            return Plan(emptyList(), scope, handled)

        val holders = states.associateBy { it.holder }
        val getters = states.mapNotNull { state -> state.getter?.let { it to state } }.toMap()
        val setters = states.mapNotNull { state -> state.setter?.let { it to state } }.toMap()
        fun member(field: EtsField, owner: IrElement) = EtsMember(self, field.symbol.name,
            field.symbol.type, language.source(owner), field.symbol.id)
        fun member(state: State, owner: IrExpression) = member(state.field, owner)
        fun assignment(call: IrCall, state: State, scope: Scope): EtsAssignment {
            val value = call.getValueArgument(0)
                ?: diagnostics.unsupported(call, "State update requires a value")
            return EtsAssignment(member(state, call), language.expression(value, scope), language.source(call))
        }
        val pagerBindings = pagerStates.associate { pager -> pager.holder to PagerStateBinding(
            member(pager.currentPage, function), pager.pageCount, member(pager.controller, function)) }
        val scrollBindings = scrollStates.associate { scroll -> scroll.holder to ScrollStateBinding(
            member(scroll.offset, function)) }
        val lazyListBindings = lazyListStates.associate { lazy -> lazy.holder to LazyListStateBinding(
            lazy.initialIndex, lazy.initialOffset, member(lazy.firstVisibleIndex, function),
            member(lazy.controller, function), lazy.initialOffsetApplied?.let { member(it, function) },
            lazy.source) }
        val rule = object : CallRule {
            private fun direct(call: IrCall): State? {
                val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                if (property !in setOf("androidx.compose.runtime.State.value", "androidx.compose.runtime.MutableState.value")) return null
                return ((call.dispatchReceiver ?: call.extensionReceiver) as? IrGetValue)?.symbol?.let(holders::get)
            }

            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                val api = symbolName(call.symbol.owner)
                val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                if (property == "androidx.compose.foundation.pager.PagerState.currentPage") {
                    val receiver = call.dispatchReceiver ?: call.extensionReceiver
                    val holder = (receiver as? IrGetValue)?.symbol
                    return holder?.let(pagerBindings::get)?.currentPage
                        ?: diagnostics.unsupported(call, "Pager currentPage requires source remembered PagerState")
                }
                if (property == "androidx.compose.foundation.ScrollState.value") {
                    val receiver = call.dispatchReceiver ?: call.extensionReceiver
                    val holder = (receiver as? IrGetValue)?.symbol
                    return holder?.let(scrollBindings::get)?.offset
                        ?: diagnostics.unsupported(call, "ScrollState value requires source remembered ScrollState")
                }
                if (property?.startsWith("androidx.compose.foundation.lazy.LazyListState.") == true) {
                    val receiver = call.dispatchReceiver ?: call.extensionReceiver
                    val binding = (receiver as? IrGetValue)?.symbol?.let(lazyListBindings::get)
                        ?: diagnostics.unsupported(call,
                            "LazyListState reads require source remembered state bound to one LazyColumn or LazyRow")
                    if (property == "androidx.compose.foundation.lazy.LazyListState.firstVisibleItemIndex")
                        return binding.firstVisibleIndex
                    diagnostics.unsupported(call,
                        "LazyListState ${property.substringAfterLast('.')} cannot be represented by ArkUI List state")
                }
                if (api in programmaticScrollApis) {
                    val receiver = call.dispatchReceiver ?: call.extensionReceiver
                    if ((receiver as? IrGetValue)?.symbol in scrollBindings)
                        diagnostics.unsupported(call, "Programmatic ScrollState scrollTo/animateScrollTo is not supported")
                }
                if (api in programmaticLazyListApis) {
                    val receiver = call.dispatchReceiver ?: call.extensionReceiver
                    if ((receiver as? IrGetValue)?.symbol in lazyListBindings)
                        diagnostics.unsupported(call,
                            "Programmatic LazyListState scrollToItem/animateScrollToItem is not supported")
                }
                getters[call.symbol]?.let { return member(it, call) }
                setters[call.symbol]?.let { return etsDiscard(assignment(call, it, scope), language.source(call)) }
                val state = direct(call) ?: return null
                return if (call.symbol.owner.valueParameters.isEmpty()) member(state, call)
                else etsDiscard(assignment(call, state, scope), language.source(call))
            }

            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                val api = symbolName(call.symbol.owner)
                val receiver = call.dispatchReceiver ?: call.extensionReceiver
                if (api in programmaticScrollApis && (receiver as? IrGetValue)?.symbol in scrollBindings)
                    diagnostics.unsupported(call, "Programmatic ScrollState scrollTo/animateScrollTo is not supported")
                if (api in programmaticLazyListApis && (receiver as? IrGetValue)?.symbol in lazyListBindings)
                    diagnostics.unsupported(call,
                        "Programmatic LazyListState scrollToItem/animateScrollToItem is not supported")
                val state = setters[call.symbol] ?: direct(call)?.takeIf { call.symbol.owner.valueParameters.isNotEmpty() }
                    ?: return null
                return listOf(EtsExpressionStatement(assignment(call, state, scope)))
            }
        }
        val loweredScope = Scope(LinkedHashMap(scope.bindings), LinkedHashMap(scope.aliases), scope.callRule,
            listOf(rule) + scope.callRules, LinkedHashMap(scope.ambientValues))
        return Plan(fields, loweredScope, handled, pagerBindings, scrollBindings, lazyListBindings)
    }

    private fun lazyListState(statement: IrStatement,
        handled: MutableSet<IrStatement>): LazyListState? {
        val declaration = statement as? IrVariable ?: return null
        val call = declaration.initializer as? IrCall ?: return null
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.lazy.rememberLazyListState") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() !in
                setOf("initialFirstVisibleItemIndex", "initialFirstVisibleItemScrollOffset"))
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Unsupported rememberLazyListState argument: ${parameter.name}; prefetch strategies are not supported")
        }
        fun initial(name: String): Pair<Int, EtsExpression> {
            val expression = argument(call, name)
            val value = if (expression == null) 0 else (expression as? IrConst)?.value as? Int
                ?: diagnostics.unsupported(expression,
                    "rememberLazyListState $name currently requires an integer literal")
            if (value < 0) diagnostics.unsupported(expression ?: call,
                "rememberLazyListState $name must be non-negative")
            return value to EtsLiteral(value, EtsTypes.NUMBER,
                expression?.let(language::source) ?: language.source(call))
        }
        val (index, initialIndex) = initial("initialFirstVisibleItemIndex")
        val (offset, initialOffset) = initial("initialFirstVisibleItemScrollOffset")
        val at = language.source(declaration)
        val firstVisibleIndex = EtsField(EtsSymbol(
            "compose-lazy-state:${at.file}:${at.start}:firstVisibleIndex",
            "${declaration.name}_firstVisibleItemIndex", EtsTypes.NUMBER, at),
            EtsLiteral(index, EtsTypes.NUMBER, at), visibility = EtsVisibility.PRIVATE, state = true)
        val controllerType = EtsNamedType("Scroller")
        val controller = EtsField(EtsSymbol(
            "compose-lazy-state:${at.file}:${at.start}:controller",
            "${declaration.name}_scroller", controllerType, at),
            EtsNew(controllerType, emptyList(), at), visibility = EtsVisibility.PRIVATE)
        val applied = if (offset == 0) null else EtsField(EtsSymbol(
            "compose-lazy-state:${at.file}:${at.start}:offsetApplied",
            "${declaration.name}_initialOffsetApplied", EtsTypes.BOOLEAN, at),
            EtsLiteral(false, EtsTypes.BOOLEAN, at), visibility = EtsVisibility.PRIVATE, state = true)
        handled += statement
        return LazyListState(declaration.symbol, initialIndex, initialOffset,
            firstVisibleIndex, controller, applied, at)
    }

    private fun scrollState(statement: IrStatement, handled: MutableSet<IrStatement>): ScrollState? {
        val declaration = statement as? IrVariable ?: return null
        val call = declaration.initializer as? IrCall ?: return null
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.rememberScrollState") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() != "initial")
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Unsupported rememberScrollState argument: ${parameter.name}")
        }
        val initialExpression = argument(call, "initial")
        val initial = if (initialExpression == null) 0 else (initialExpression as? IrConst)?.value as? Int
            ?: diagnostics.unsupported(initialExpression,
                "ScrollState initial offset currently requires an integer literal")
        if (initial < 0)
            diagnostics.unsupported(initialExpression ?: call, "ScrollState initial offset must be non-negative")
        val at = language.source(declaration)
        val name = "${declaration.name}_offset"
        val field = EtsField(EtsSymbol("compose-scroll:${at.file}:${at.start}:offset",
            name, EtsTypes.NUMBER, at), EtsLiteral(initial, EtsTypes.NUMBER, at),
            visibility = EtsVisibility.PRIVATE, state = true)
        handled += statement
        return ScrollState(declaration.symbol, field)
    }

    private fun pagerState(statement: IrStatement, handled: MutableSet<IrStatement>): PagerState? {
        val declaration = statement as? IrVariable ?: return null
        val call = declaration.initializer as? IrCall ?: return null
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.pager.rememberPagerState") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() !in setOf("initialPage", "pageCount"))
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Unsupported rememberPagerState argument: ${parameter.name}")
        }
        val pageCountLambda = argument(call, "pageCount")
            ?: diagnostics.unsupported(call, "rememberPagerState requires pageCount")
        val pageCountFunction = (pageCountLambda as? IrFunctionExpression)?.function
            ?: diagnostics.unsupported(pageCountLambda, "Pager pageCount requires a direct lambda")
        val pageCountResult = (pageCountFunction.body as? IrBlockBody)?.statements?.singleOrNull()
            ?: diagnostics.unsupported(pageCountLambda, "Pager pageCount requires one direct result")
        val pageCountExpression = (pageCountResult as? IrReturn)?.value ?: pageCountResult as? IrExpression
            ?: diagnostics.unsupported(pageCountResult, "Pager pageCount requires an integer result")
        val count = (pageCountExpression as? IrConst)?.value as? Int
        if (count == null || count <= 0)
            diagnostics.unsupported(pageCountExpression, "Pager pageCount currently requires a positive integer literal")
        val initialExpression = argument(call, "initialPage")
        val initial = if (initialExpression == null) 0 else (initialExpression as? IrConst)?.value as? Int
            ?: diagnostics.unsupported(initialExpression, "Pager initialPage currently requires an integer literal")
        if (initial !in 0 until count)
            diagnostics.unsupported(initialExpression ?: call, "Pager initialPage must be within pageCount")
        val at = language.source(declaration)
        val currentName = "${declaration.name}_currentPage"
        val current = EtsField(EtsSymbol("compose-pager:${at.file}:${at.start}:currentPage",
            currentName, EtsTypes.NUMBER, at), EtsLiteral(initial, EtsTypes.NUMBER, at),
            visibility = EtsVisibility.PRIVATE, state = true)
        val controllerType = EtsNamedType("SwiperController")
        val controllerName = "${declaration.name}_controller"
        val controller = EtsField(EtsSymbol("compose-pager:${at.file}:${at.start}:controller",
            controllerName, controllerType, at), EtsNew(controllerType, emptyList(), at),
            visibility = EtsVisibility.PRIVATE)
        handled += statement
        return PagerState(declaration.symbol, current,
            EtsLiteral(count, EtsTypes.NUMBER, language.source(pageCountExpression)), controller)
    }

    private fun state(statement: IrStatement, scope: Scope, handled: MutableSet<IrStatement>): State? {
        val declaration = when (statement) {
            is IrVariable -> StateDeclaration(statement.name.asString(), statement, statement.initializer,
                statement.symbol)
            is IrLocalDelegatedProperty -> StateDeclaration(statement.name.asString(), statement,
                statement.delegate.initializer, statement.delegate.symbol, statement.getter.symbol, statement.setter?.symbol)
            else -> return null
        }
        val initial = rememberedState(declaration.initializer ?: return null) ?: return null
        val targetType = when {
            initial.type.isBoolean() && initial is IrConst && initial.value is Boolean -> EtsTypes.BOOLEAN
            initial.type.isInt() && initial is IrConst && initial.value is Int -> EtsTypes.NUMBER
            initial.type.isString() && initial is IrConst && initial.value is String -> EtsTypes.STRING
            else -> diagnostics.unsupported(initial,
                "Compose state initially supports only direct Boolean, Int, and String initializers")
        }
        val at = language.source(declaration.owner)
        val targetName = "__etsState_${declaration.name}"
        val field = EtsField(EtsSymbol("compose-state:${at.file}:${at.start}:${declaration.name}",
            targetName, targetType, at), language.expression(initial, scope),
            visibility = EtsVisibility.PRIVATE, state = true)
        handled += statement
        return State(field, declaration.holder, declaration.getter, declaration.setter)
    }

    private data class StateDeclaration(
        val name: String,
        val owner: IrDeclaration,
        val initializer: IrExpression?,
        val holder: IrValueSymbol,
        val getter: IrSimpleFunctionSymbol? = null,
        val setter: IrSimpleFunctionSymbol? = null,
    )

    private fun rememberedState(expression: IrExpression): IrExpression? {
        val call = expression as? IrCall ?: return null
        val api = symbolName(call.symbol.owner)
        if (api == "androidx.compose.runtime.saveable.rememberSaveable")
            diagnostics.unsupported(call, "rememberSaveable is outside the Compose state Core Profile")
        if (api in setOf("androidx.compose.runtime.mutableStateOf", "androidx.compose.runtime.derivedStateOf"))
            diagnostics.unsupported(call, "Compose state declaration requires remember { mutableStateOf(initial) }")
        if (api != "androidx.compose.runtime.remember") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() != "calculation")
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Compose state remember does not support keys")
        }
        val calculation = argument(call, "calculation")
            ?: diagnostics.unsupported(call, "Compose state remember requires a calculation")
        val function = (calculation as? IrFunctionExpression)?.function
            ?: diagnostics.unsupported(calculation, "Compose state remember requires a direct lambda")
        val result = (function.body as? IrBlockBody)?.statements?.singleOrNull() as? IrReturn
            ?: diagnostics.unsupported(calculation, "Compose state remember requires one direct result")
        val factory = result.value as? IrCall
            ?: diagnostics.unsupported(result.value, "Compose state remember requires mutableStateOf")
        if (symbolName(factory.symbol.owner) != "androidx.compose.runtime.mutableStateOf")
            diagnostics.unsupported(factory, "Compose state remember supports only mutableStateOf")
        factory.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (factory.getValueArgument(index) != null && parameter.name.asString() != "value")
                diagnostics.unsupported(factory.getValueArgument(index)!!,
                    "Compose state mutableStateOf does not support a custom mutation policy")
        }
        return argument(factory, "value")
            ?: diagnostics.unsupported(factory, "Compose state mutableStateOf requires an initial value")
    }

    private companion object {
        val programmaticScrollApis = setOf(
            "androidx.compose.foundation.ScrollState.scrollTo",
            "androidx.compose.foundation.ScrollState.animateScrollTo")
        val programmaticLazyListApis = setOf(
            "androidx.compose.foundation.lazy.LazyListState.scrollToItem",
            "androidx.compose.foundation.lazy.LazyListState.animateScrollToItem")
    }
}
