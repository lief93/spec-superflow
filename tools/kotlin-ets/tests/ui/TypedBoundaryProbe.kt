@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package ui.test

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.expressions.IrBody
import org.jetbrains.kotlin.ir.expressions.IrExpression
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol

/** Inspect the actual UI/language seam while lowering official source IR. */
private class ObservedLanguage(private val delegate: Language) : Language by delegate {
    val overrides = mutableListOf<EtsExpression>()
    val effects = mutableListOf<EtsStatement>()
    val bindings = linkedMapOf<IrValueSymbol, EtsReference>()

    private fun observed(scope: Scope): Scope {
        scope.bindings.forEach { (sourceSymbol, value) ->
            if (value is EtsReference) {
                val previous = bindings.putIfAbsent(sourceSymbol, value)
                check(previous == null || previous.symbol == value.symbol)
                check(value.source.file != null && value.source.start >= 0)
                check(value.source.end > value.source.start)
                check(value.symbol.name.none { it in ".()[]" })
            } else {
                check(value.source.file != null && value.source.start >= 0)
                check(value.source.end > value.source.start)
            }
        }
        val original = scope.callRule
        return scope.fork().also { child ->
            child.callRule = object : CallRule {
                override fun lower(call: IrCall, language: Language, scope: Scope) =
                    original?.lower(call, language, scope)?.also { overrides += it }
                override fun lowerStatement(call: IrCall, language: Language, scope: Scope) =
                    original?.lowerStatement(call, language, scope)?.also { effects += it }
            }
        }
    }

    override fun expression(expression: IrExpression, scope: Scope): EtsExpression =
        delegate.expression(expression, observed(scope))

    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> =
        delegate.statements(body, observed(scope))

    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction =
        delegate.function(function, observed(scope))
}

fun main(args: Array<String>) {
    val detached = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { module ->
        val diagnostics = DiagnosticSink()
        val backend = EtsBackend(diagnostics, listOf(StandardLibraryRules(), ComposeColorValueRule(),
            ComposeColorSchemeRule(), ComposeMaterialThemeValueRule(), ComposeTypographyRule(),
            ComposeFontRule(FontResources()), ComposeLineHeightStyleRule(), ComposeTextStyleRule(), ComposeDimensionRule(),
            ComposeCompositionLocalRule(diagnostics), ComposeShapeRule(), ComposeButtonColorsRule()))
        backend.validateSource(module)
        val observed = ObservedLanguage(backend.language)
        val program = ComposeLowering(observed, diagnostics).lower(module, "sample.Page")
        EtsValidator().validate(program)
        val component = program.files.flatMap { it.declarations }.filterIsInstance<EtsClass>().single { it.component }
        check(component.name == "Page" && component.entry)
        check(component.members.filterIsInstance<EtsFunction>().any { it.builder })
        check(component.members.filterIsInstance<EtsField>().any { it.state })
        val nodes = mutableListOf<EtsNode>()
        program.files.flatMap { it.declarations }.forEach { walkEts(it, nodes::add) }
        check(nodes.any { it is EtsUiElement } && nodes.any { it is EtsUiForEach } && nodes.any { it is EtsConditional })
        check(program.imports.isNotEmpty())
        check(observed.bindings.values.map { it.symbol.id }.distinct().size == observed.bindings.size)
        check(observed.bindings.values.any {
            it.type == EtsNamedType("WrappedBuilder", listOf(EtsTupleType(listOf(materialContextType))))
        })
        val sourceFile = module.files.single()
        val sourceModel = sourceFile.declarations.filterIsInstance<IrClass>().single { it.name.asString() == "Model" }
        val modelType = etsClassSymbol(sourceModel.name.asString(),
            SourceSpan(sourceFile.fileEntry.name, sourceModel.startOffset, sourceModel.endOffset)).type
        check(observed.bindings.values.any { it.symbol.name == "model" && it.type == modelType })
        val reads = observed.overrides.filterIsInstance<EtsMember>()
        check(reads.any { it.name == "pagerState_currentPage" && it.type == EtsTypes.NUMBER })
        check(reads.any { it.name == "callbackCount" && it.type == EtsTypes.NUMBER })
        val discarded = observed.overrides.filterIsInstance<EtsCall>().filter { it.type == EtsTypes.VOID }
            .mapNotNull { it.callee as? EtsLambda }
        val writes = discarded.flatMap { it.body }.filterIsInstance<EtsExpressionStatement>()
            .mapNotNull { it.expression as? EtsAssignment }
        check(writes.any { (it.target as? EtsMember)?.name == "callbackCount" })
        val calls = observed.effects.filterIsInstance<EtsExpressionStatement>().mapNotNull { it.expression as? EtsCall }
        check(calls.any {
            val member = it.callee as? EtsMember
            member?.name == "changeIndex" && member.receiver is EtsMember &&
                it.arguments.last() == EtsLiteral(true, EtsTypes.BOOLEAN, it.source)
        })
        check(observed.overrides.all { it.source.file == args[1] && it.source.start >= 0 && it.source.end > it.source.start })
        check(observed.effects.all { it.source.file == args[1] && it.source.start >= 0 && it.source.end > it.source.start })
        val runtime = ComposeRuntime(EtsRuntimeSupport { emptyList() })
        val support = runtime.declarations(program)
        check(support.none { "class __etsMaterialTypography" in it })
        check(support.count { "function __etsNearestTouch" in it } == 1)
        val origin = SourceSpan(args[1], 0, 1)
        val styleType = EtsNamedType("__etsMaterialTypography", symbolId = "compose:materialTypography", external = true)
        val invalidStyle = EtsNew(styleType, listOf(EtsLiteral("bad", EtsTypes.STRING, origin)), origin)
        val invalid = EtsProgram(listOf(EtsFile(args[1], listOf(EtsFunction("badStyle", emptyList(), styleType,
            listOf(EtsReturn(invalidStyle, origin)), origin)))))
        check(runCatching { runtime.declarations(invalid) }.exceptionOrNull() is InvalidTarget)
        println("PASS typed UI bindings, symbol identity/source, tuple slots, state members/assignments, pager call/literal")
        program
    }
    EtsValidator().validate(detached)
    check(ComposeRuntime(EtsRuntimeSupport { emptyList() }).declarations(detached).isNotEmpty())
    println("PASS detached UI target remains valid after official frontend disposal")
    verifyUnifiedRules(args[0], args[2])
}

private fun verifyUnifiedRules(classpath: String, file: String) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", classpath, file)) { module ->
        val diagnostics = DiagnosticSink()
        val ordinary = EtsBackend(diagnostics, listOf(StandardLibraryRules(),
            ComposeCompositionLocalRule(diagnostics), ComposeShapeRule()))
        val unsupported = runCatching { ComposeLowering(ordinary.language, diagnostics).lower(module, "unifiedapi.RulePage") }.exceptionOrNull()
        check(unsupported is Unsupported && "CircularProgressIndicator" in unsupported.message.orEmpty())
        var values = 0
        var controls = 0
        val rule = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                val property = call.symbol.owner.correspondingPropertySymbol?.owner ?: return null
                if (symbolName(property) != "androidx.compose.runtime.currentCompositeKeyHash") return null
                values++
                return EtsLiteral(73, EtsTypes.NUMBER, language.source(call))
            }
            override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                if (symbolName(call.symbol.owner) != "androidx.compose.material3.CircularProgressIndicator") return null
                controls++
                val source = language.source(call)
                val symbol = EtsSymbol("test:Divider", "Divider", EtsFunctionType(emptyList(), EtsTypes.VOID), source, external = true)
                return listOf(EtsUiElement(EtsCall(EtsReference(symbol), emptyList(), EtsTypes.VOID, source)))
            }
        }
        val backend = EtsBackend(diagnostics, listOf(rule, StandardLibraryRules(),
            ComposeCompositionLocalRule(diagnostics), ComposeShapeRule()))
        val result = ComposeLowering(backend.language, diagnostics).lower(module, "unifiedapi.RulePage")
        EtsValidator().validate(result)
        check(values == 1 && controls == 1) { "Registered ordinary/UI rules must both run exactly once" }
        val nodes = mutableListOf<EtsNode>()
        result.files.flatMap { it.declarations }.forEach { walkEts(it, nodes::add) }
        check(nodes.any { it is EtsLiteral && it.value == 73 })
        check(nodes.filterIsInstance<EtsUiElement>().any { (it.call.callee as? EtsReference)?.symbol?.id == "test:Divider" })
        println("PASS one backend rule registration handles both real Compose value and UI APIs without a printer")
    }
}
