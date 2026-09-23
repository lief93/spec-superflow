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
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid

/** Extracts the small Compose state profile before neutral widget adaptation. */
class ComposeStateLowering(private val language: Language, private val diagnostics: DiagnosticSink) {
    data class Plan(
        val fields: List<EtsField>,
        val scope: Scope,
        val handledStatements: Set<IrStatement>,
        val pagers: Map<IrValueSymbol, PagerStateBinding> = emptyMap(),
        val scrolls: Map<IrValueSymbol, ScrollStateBinding> = emptyMap(),
        val lazyLists: Map<IrValueSymbol, LazyListStateBinding> = emptyMap(),
        val imports: List<EtsImport> = emptyList(),
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
        val coroutineScopes = mutableSetOf<IrValueSymbol>()
        val fields = mutableListOf<EtsField>()
        statements.forEach { statement ->
            val state = state(statement, scope, handled)
            if (state != null) {
                states += state
                fields += state.field
            } else {
                val pager = pagerState(statement, scope, handled)
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
                    } ?: coroutineScope(statement, handled)?.let(coroutineScopes::add)
                }
            }
        }

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
        var hasLazyListEffect = false
        function.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
            override fun visitCall(expression: IrCall) {
                if (symbolName(expression.symbol.owner) in programmaticLazyListApis) hasLazyListEffect = true
                expression.acceptChildrenVoid(this)
            }
        })
        val rule = object : CallRule {
            private fun direct(call: IrCall): State? {
                val property = call.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
                if (property !in setOf("androidx.compose.runtime.State.value", "androidx.compose.runtime.MutableState.value")) return null
                return ((call.dispatchReceiver ?: call.extensionReceiver) as? IrGetValue)?.symbol?.let(holders::get)
            }

            private fun lazyList(call: IrCall): LazyListStateBinding {
                val receiver = call.dispatchReceiver ?: call.extensionReceiver
                return (receiver as? IrGetValue)?.symbol?.let(lazyListBindings::get)
                    ?: diagnostics.unsupported(receiver ?: call,
                        "Programmatic LazyListState scrolling requires source remembered state bound to its typed Scroller")
            }

            private fun lazyListEffect(call: IrCall, language: Language,
                scope: Scope): List<EtsStatement> {
                val binding = lazyList(call)
                val indexSource = argument(call, "index")
                    ?: diagnostics.unsupported(call, "LazyListState scrolling requires an index")
                ((indexSource as? IrConst)?.value as? Int)?.takeIf { it < 0 }?.let {
                    diagnostics.unsupported(indexSource,
                        "Negative LazyListState index is rejected by Compose but silently ignored by ArkUI scrollToIndex")
                }
                val offsetSource = argument(call, "scrollOffset")
                val at = language.source(call)
                val index = EtsSymbol("compose-lazy-effect:${at.file}:${at.start}:index",
                    "__etsLazyIndex${at.start}", EtsTypes.NUMBER, language.source(indexSource))
                val offset = EtsSymbol("compose-lazy-effect:${at.file}:${at.start}:offset",
                    "__etsLazyOffset${at.start}", EtsTypes.NUMBER,
                    offsetSource?.let(language::source) ?: at)
                val indexValue = language.expression(indexSource, scope)
                val offsetValue = offsetSource?.let { language.expression(it, scope) }
                    ?: EtsLiteral(0, EtsTypes.NUMBER, at)
                val lengthType = EtsNamedType("LengthMetrics", external = true)
                val lengthFactory = EtsReference(EtsSymbol("arkui:LengthMetrics", "LengthMetrics",
                    EtsNamedType("LengthMetricsConstructor", external = true), at, external = true))
                val pixels = EtsCall(EtsMember(lengthFactory, "px",
                    EtsFunctionType(listOf(EtsTypes.NUMBER), lengthType), at),
                    listOf(EtsReference(offset)), lengthType, at)
                val options = EtsObject(linkedMapOf("extraOffset" to pixels),
                    EtsRecordType("ScrollToIndexOptions", linkedMapOf("extraOffset" to lengthType)), at)
                val alignType = EtsNamedType("ScrollAlign")
                val start = EtsMember(EtsReference(EtsSymbol("arkui:ScrollAlign", "ScrollAlign",
                    alignType, at, external = true)), "START", alignType, at)
                val method = EtsMember(binding.controller, "scrollToIndex",
                    EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.BOOLEAN, alignType,
                        options.type), EtsTypes.VOID), at)
                val smooth = symbolName(call.symbol.owner) ==
                    "androidx.compose.foundation.lazy.LazyListState.animateScrollToItem"
                fun nonNegative(value: EtsSymbol, label: String): EtsIf {
                    val fail = EtsCall(EtsReference(EtsSymbol("stdlib:__etsIllegalArgumentException",
                        "__etsIllegalArgumentException",
                        EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NEVER), at, external = true)),
                        listOf(EtsLiteral("LazyListState $label must be non-negative.",
                            EtsTypes.STRING, at)), EtsTypes.NEVER, at)
                    return EtsIf(listOf(EtsBranch(EtsBinary("<", EtsReference(value),
                        EtsLiteral(0, EtsTypes.NUMBER, at), EtsTypes.BOOLEAN, at),
                        listOf(EtsExpressionStatement(fail)))), at)
                }
                return listOf(
                    EtsVariable(index, indexValue, mutable = false),
                    EtsVariable(offset, offsetValue, mutable = false),
                    nonNegative(index, "index"),
                    nonNegative(offset, "scrollOffset"),
                    EtsExpressionStatement(EtsCall(method, listOf(EtsReference(index),
                        EtsLiteral(smooth, EtsTypes.BOOLEAN, at), start, options), EtsTypes.VOID, at)),
                )
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
                    lazyList(call)
                    diagnostics.unsupported(call,
                        "LazyListState scrollToItem/animateScrollToItem is an effect and cannot produce a target value")
                }
                if (api == coroutineLaunchApi &&
                    ((call.dispatchReceiver ?: call.extensionReceiver) as? IrGetValue)?.symbol in coroutineScopes) {
                    diagnostics.unsupported(call,
                        "Coroutine launch is an effect and cannot produce a target Job value")
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
                if (api in programmaticLazyListApis) return lazyListEffect(call, language, scope)
                if (api == coroutineLaunchApi && (receiver as? IrGetValue)?.symbol in coroutineScopes) {
                    call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
                        call.getValueArgument(index)?.takeIf { parameter.name.asString() != "block" }?.let {
                            diagnostics.unsupported(it,
                                "Coroutine launch ${parameter.name} semantics cannot be preserved by an ArkUI event effect")
                        }
                    }
                    val block = lambda(argument(call, "block"), scope)
                        ?: diagnostics.unsupported(call, "Coroutine launch requires a direct suspend block")
                    return language.statements(block.body
                        ?: diagnostics.unsupported(block, "Coroutine launch block has no body"), scope.fork())
                }
                val state = setters[call.symbol] ?: direct(call)?.takeIf { call.symbol.owner.valueParameters.isNotEmpty() }
                    ?: return null
                return listOf(EtsExpressionStatement(assignment(call, state, scope)))
            }
        }
        val loweredScope = Scope(LinkedHashMap(scope.bindings), LinkedHashMap(scope.aliases), scope.callRule,
            listOf(rule) + scope.callRules, LinkedHashMap(scope.ambientValues), LinkedHashSet(scope.semanticFlags))
        val imports = if (hasLazyListEffect && lazyListStates.isNotEmpty())
            listOf(EtsImport("@kit.ArkUI", "LengthMetrics")) else emptyList()
        return Plan(fields, loweredScope, handled, pagerBindings, scrollBindings, lazyListBindings, imports)
    }

    private fun coroutineScope(statement: IrStatement,
        handled: MutableSet<IrStatement>): IrValueSymbol? {
        val declaration = statement as? IrVariable ?: return null
        val call = declaration.initializer as? IrCall ?: return null
        if (symbolName(call.symbol.owner) != "androidx.compose.runtime.rememberCoroutineScope") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            call.getValueArgument(index)?.let {
                diagnostics.unsupported(it,
                    "rememberCoroutineScope ${parameter.name} semantics cannot be represented by an ArkUI event effect")
            }
        }
        handled += statement
        return declaration.symbol
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

    private fun pagerState(statement: IrStatement, scope: Scope,
        handled: MutableSet<IrStatement>): PagerState? {
        val declaration = statement as? IrVariable ?: return null
        val call = declaration.initializer as? IrCall ?: return null
        if (symbolName(call.symbol.owner) != "androidx.compose.foundation.pager.rememberPagerState") return null
        call.symbol.owner.valueParameters.forEachIndexed { index, parameter ->
            if (call.getValueArgument(index) != null && parameter.name.asString() !in
                setOf("initialPage", "initialPageOffsetFraction", "pageCount"))
                diagnostics.unsupported(call.getValueArgument(index)!!,
                    "Unsupported rememberPagerState argument: ${parameter.name}")
        }
        argument(call, "initialPageOffsetFraction")?.let { expression ->
            val value = (expression as? IrConst)?.value as? Number
            if (value?.toDouble() != 0.0) diagnostics.unsupported(expression,
                "Pager initialPageOffsetFraction requires 0 because ArkUI Swiper starts on whole pages")
        }
        val pageCountLambda = argument(call, "pageCount")
            ?: diagnostics.unsupported(call, "rememberPagerState requires pageCount")
        val pageCountFunction = (pageCountLambda as? IrFunctionExpression)?.function
            ?: diagnostics.unsupported(pageCountLambda, "Pager pageCount requires a direct lambda")
        val pageCountResult = (pageCountFunction.body as? IrBlockBody)?.statements?.singleOrNull()
            ?: diagnostics.unsupported(pageCountLambda, "Pager pageCount requires one direct result")
        val pageCountExpression = (pageCountResult as? IrReturn)?.value ?: pageCountResult as? IrExpression
            ?: diagnostics.unsupported(pageCountResult, "Pager pageCount requires an integer result")
        if (!pageCountExpression.type.isInt())
            diagnostics.unsupported(pageCountExpression, "Pager pageCount requires Int")
        val count = (pageCountExpression as? IrConst)?.value as? Int
        if (count != null && count <= 0)
            diagnostics.unsupported(pageCountExpression, "Pager pageCount must be positive")
        val pageCount = language.expression(pageCountExpression, scope)
        val initialExpression = argument(call, "initialPage")
        val initial = if (initialExpression == null) 0 else (initialExpression as? IrConst)?.value as? Int
            ?: diagnostics.unsupported(initialExpression, "Pager initialPage currently requires an integer literal")
        if (initial < 0 || count != null && initial >= count)
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
        return PagerState(declaration.symbol, current, pageCount, controller)
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
        const val coroutineLaunchApi = "kotlinx.coroutines.launch"
    }
}
