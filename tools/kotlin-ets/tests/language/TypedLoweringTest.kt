@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.ir.IrElement

fun main(args: Array<String>) {
    var borrowed: KotlinFrontendSession? = null
    withKotlinFrontend(listOf(args[0], args[2], "-no-stdlib", "-no-reflect", "-classpath", args[1])) { session ->
        borrowed = session
        val module = session.module
        val file = module.files.single { it.fileEntry.name == args[0] }
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>().associateBy { it.name.asString() }
        val diagnostics = DiagnosticSink(file.fileEntry.name)
        val helperBody = session.bodies.resolve(functions.getValue("helper").symbol) as FunctionBody.Available
        check(helperBody.origin == FunctionBody.Origin.Source)
        check(helperBody.declaration === functions.getValue("helper"))
        check(helperBody.body === functions.getValue("helper").body)
        check(helperBody.source.file == args[2])
        var signatures = 0
        functions.getValue("effectOnly").acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrCall) {
                    check(session.bodies.resolve(element.symbol) is FunctionBody.Unavailable)
                    signatures++
                }
                element.acceptChildrenVoid(this)
            }
        })
        check(signatures == 1)
        var ruleCalls = 0
        val rule = object : CallRule {
            override fun lower(call: org.jetbrains.kotlin.ir.expressions.IrCall, language: Language, scope: Scope): EtsExpression? {
                ruleCalls++
                return EtsLiteral(11, EtsTypes.NUMBER, language.source(call))
            }
        }
        val lowering = LanguageLowering(diagnostics, listOf(rule))
        fun validate(function: EtsFunction) = EtsValidator().validate(EtsProgram(listOf(EtsFile(args[0], listOf(function)))))
        val identity = lowering.function(functions.getValue("identity"))
        validate(identity)
        val local = identity.body.first() as EtsVariable
        check((local.initializer as EtsReference).symbol === identity.parameters.single().symbol)
        check(((identity.body.last() as EtsReturn).value as EtsReference).symbol === local.symbol)
        check(!local.symbol.external && !identity.parameters.single().symbol.external)
        check(local.symbol.source.file == args[0] && local.symbol.source.start >= 0)

        val override = Scope(callRule = CallRule { call, _, _ -> EtsLiteral(23, EtsTypes.NUMBER, lowering.source(call)) })
        val adapted = lowering.function(functions.getValue("adapted"), override)
        check(((adapted.body.single() as EtsReturn).value as EtsLiteral).value == 23)
        check(ruleCalls == 0)
        validate(adapted)
        val ruled = lowering.function(functions.getValue("adapted"))
        check(((ruled.body.single() as EtsReturn).value as EtsLiteral).value == 11)
        check(ruleCalls == 1)
        validate(ruled)

        fun rejects(name: String, scope: Scope, expected: String, emitter: LanguageLowering = lowering) {
            val failure = runCatching { emitter.function(functions.getValue(name), scope) }.exceptionOrNull()
            check(failure is Unsupported && failure.diagnostic.message.contains(expected)) { "Expected $expected; got $failure" }
            check(failure.diagnostic.source.file == args[0])
            check(failure.diagnostic.source.start >= 0 && failure.diagnostic.source.end > failure.diagnostic.source.start)
        }
        rejects("adapted", Scope(callRule = CallRule { call, _, _ -> EtsLiteral("wrong", EtsTypes.STRING, lowering.source(call)) }), "Invalid call adapter result")
        val badRule = object : CallRule {
            override fun lower(call: org.jetbrains.kotlin.ir.expressions.IrCall, language: Language, scope: Scope) =
                EtsLiteral("wrong", EtsTypes.STRING, language.source(call))
        }
        rejects("adapted", Scope(), "Invalid call adapter result", LanguageLowering(diagnostics, listOf(badRule)))

        val plain = LanguageLowering(diagnostics, emptyList())
        val omitted = plain.function(functions.getValue("omitted"))
        val call = (omitted.body.single() as EtsReturn).value as EtsCall
        check(call.arguments.size == 2 && call.arguments[1] is EtsUndefined)
        check(call.callee.type == EtsFunctionType(listOf(EtsTypes.NUMBER, EtsTypes.NUMBER), EtsTypes.NUMBER))
        val defaults = plain.function(functions.getValue("defaults"))
        check((call.callee as EtsReference).symbol == defaults.symbol)
        check(!call.callee.symbol.external)
        EtsValidator().validate(EtsProgram(listOf(EtsFile(args[0], listOf(defaults, omitted)))))
        check(runCatching { validate(omitted) }.exceptionOrNull() is InvalidTarget)
        val across = plain.function(functions.getValue("acrossFile"))
        val helper = plain.function(functions.getValue("helper"))
        val helperReference = ((across.body.single() as EtsReturn).value as EtsCall).callee as EtsReference
        check(helperReference.symbol == helper.symbol && helperReference.symbol.source.file == args[2])
        check(helperReference.source.file == args[0])
        EtsValidator().validate(EtsProgram(listOf(EtsFile(args[0], listOf(across)), EtsFile(args[2], listOf(helper)))))
        val singleton = plain.clazz(file.declarations.filterIsInstance<IrClass>().single())
        val singletonUse = plain.function(functions.getValue("singletonReference"))
        val getter = ((singletonUse.body.single() as EtsReturn).value as EtsCall).callee as EtsMember
        check((getter.receiver as EtsReference).symbol == singleton.symbol && !getter.receiver.symbol.external)
        EtsValidator().validate(EtsProgram(listOf(EtsFile(args[0], listOf(singleton, singletonUse)))))
        println("PASS typed symbols, default slots, adapter precedence and result rejection")

        var effectCalls = 0
        val effects = Scope(callRule = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement> {
                check(symbolName(call.symbol.owner) in setOf("java.time.Instant.now", "java.lang.System.gc"))
                val body = session.bodies.resolve(call.symbol) as FunctionBody.Unavailable
                check(body.reason == FunctionBody.Reason.NON_INLINE_BINARY)
                check(call.symbol.owner.body == null)
                effectCalls++
                return listOf(EtsExpressionStatement(EtsLiteral(19, EtsTypes.NUMBER, plain.source(call))))
            }
        })
        check(effects.fork().callRule === effects.callRule)
        validate(plain.function(functions.getValue("effectOnly"), effects))
        validate(plain.function(functions.getValue("directEffect"), effects))
        validate(plain.function(functions.getValue("coercedEffect"), effects))
        check(effectCalls == 3)
        rejects("storedEffect", effects, "java.time.Instant.now", plain)
        rejects("returnedEffect", effects, "java.time.Instant.now", plain)
        check(effectCalls == 3)
        println("PASS statement-only effects, Unit coercion, stored/returned external values reject")
        var expressionEffects = 0
        val expressionEffect = Scope(callRule = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement> {
                expressionEffects++
                return listOf(EtsExpressionStatement(EtsLiteral(31, EtsTypes.NUMBER, language.source(call))))
            }
        })
        validate(plain.function(functions.getValue("expressionEffect"), expressionEffect))
        check(expressionEffects == 1)
        println("PASS expression-body Unit consumes a statement effect without fabricating a value")
        val effectRule = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                effectCalls++
                return listOf(EtsExpressionStatement(EtsLiteral(19, EtsTypes.NUMBER, language.source(call))))
            }
        }
        val registeredEffects = LanguageLowering(diagnostics, listOf(effectRule))
        validate(registeredEffects.function(functions.getValue("effectOnly")))
        validate(registeredEffects.function(functions.getValue("coercedEffect")))
        check(effectCalls == 5)
        rejects("storedEffect", Scope(), "java.time.Instant.now", registeredEffects)
        rejects("returnedEffect", Scope(), "java.time.Instant.now", registeredEffects)
        check(effectCalls == 5)
        val emptyEffect = Scope(callRule = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
            override fun lowerStatement(call: IrCall, language: Language, scope: Scope) = emptyList<EtsStatement>()
        })
        rejects("directEffect", emptyEffect, "Empty statement adapter result", registeredEffects)
        check(effectCalls == 5) { "Rejected empty effect must not fall through" }
        val valueBeforeEffect = Scope(callRule = CallRule { call, language, _ ->
            EtsCall(EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, language.source(call)),
                emptyList(), EtsTypes.VOID, language.source(call))
        })
        validate(registeredEffects.function(functions.getValue("directEffect"), valueBeforeEffect))
        check(effectCalls == 5) { "Local value rule must take precedence over global effects" }
        println("PASS registered effects share the same value/statement boundary")

        fun sourceCall(name: String): IrCall {
            val calls = mutableListOf<IrCall>()
            functions.getValue(name).acceptChildrenVoid(object : IrElementVisitorVoid {
                override fun visitElement(element: IrElement) {
                    if (element is IrCall) calls += element
                    element.acceptChildrenVoid(this)
                }
            })
            return calls.single()
        }
        val numberCall = sourceCall("adapted")
        val unitCall = sourceCall("directEffect")
        check(session.bodies.resolve(unitCall.symbol) ==
            FunctionBody.Unavailable(FunctionBody.Reason.NON_INLINE_BINARY)) {
            "Successful target replacement must not fabricate a Kotlin body"
        }
        val trace = mutableListOf<String>()
        fun recordingRule(name: String, value: EtsExpression? = null,
            statements: List<EtsStatement>? = null, ui: List<EtsStatement>? = null) = object : CallRule {
            override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
                trace += "$name.value"; return value
            }
            override fun lowerStatement(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                trace += "$name.statement"; return statements
            }
            override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
                trace += "$name.ui"; return ui
            }
        }
        val number = EtsLiteral(37, EtsTypes.NUMBER, plain.source(numberCall))
        val marker = listOf<EtsStatement>(EtsExpressionStatement(number))
        val global = recordingRule("global", number, marker, marker)
        val dispatch = LanguageLowering(diagnostics, listOf(global))
        check(dispatch.callRules.single() === global)
        val scopedRules = listOf(recordingRule("first"), recordingRule("second", number, marker, marker))
        val orderedScope = Scope(callRule = recordingRule("override"), callRules = scopedRules)
        check(orderedScope.fork().callRule === orderedScope.callRule)
        check(orderedScope.fork().callRules === scopedRules)
        check(adaptCall(numberCall, dispatch, orderedScope, CallContext.VALUE) { EtsTypes.NUMBER } == CallResult.Value(number))
        check(trace == listOf("override.value", "first.value", "second.value")); trace.clear()
        check(adaptCall(numberCall, dispatch, orderedScope, CallContext.STATEMENT) { EtsTypes.NUMBER } == CallResult.Statements(marker))
        check(trace == listOf("override.statement", "override.value", "first.statement", "first.value", "second.statement"))
        trace.clear()
        check(adaptCall(unitCall, dispatch, orderedScope, CallContext.UI) == CallResult.Ui(marker))
        check(trace == listOf("override.ui", "first.ui", "second.ui")); trace.clear()
        check(adaptCall(numberCall, dispatch, Scope(), CallContext.VALUE) { EtsTypes.NUMBER } == CallResult.Value(number))
        check(trace == listOf("global.value")); trace.clear()
        check(adaptCall(unitCall, dispatch, Scope(), CallContext.UI) == CallResult.Ui(marker))
        check(trace == listOf("global.ui")); trace.clear()

        val onlyUi = Scope(callRules = listOf(recordingRule("uiOnly", ui = marker)))
        check(adaptCall(numberCall, plain, onlyUi, CallContext.VALUE) { EtsTypes.NUMBER } == null)
        check(trace == listOf("uiOnly.value")); trace.clear()
        check(adaptCall(unitCall, plain, onlyUi, CallContext.STATEMENT) { EtsTypes.VOID } == null)
        check(trace == listOf("uiOnly.statement", "uiOnly.value")); trace.clear()
        val ordinaryOnly = Scope(callRules = listOf(recordingRule("ordinary", statements = marker)))
        check(adaptCall(unitCall, plain, ordinaryOnly, CallContext.UI) == null)
        check(trace == listOf("ordinary.ui")); trace.clear()
        val voidValue = EtsCall(EtsLambda(emptyList(), emptyList(), EtsTypes.VOID, plain.source(unitCall)),
            emptyList(), EtsTypes.VOID, plain.source(unitCall))
        val voidOnly = Scope(callRules = listOf(recordingRule("void", value = voidValue)))
        check(adaptCall(unitCall, plain, voidOnly, CallContext.UI) == null)
        check(trace == listOf("void.ui")); trace.clear()
        check(adaptCall(unitCall, plain, voidOnly, CallContext.STATEMENT) { EtsTypes.VOID } ==
            CallResult.Statements(listOf(EtsExpressionStatement(voidValue))))
        check(trace == listOf("void.statement", "void.value")); trace.clear()
        check(adaptCall(numberCall, dispatch, Scope(callRule = recordingRule("local", number)),
            CallContext.STATEMENT) { EtsTypes.NUMBER } == CallResult.Value(number))
        check(trace == listOf("local.statement", "local.value")); trace.clear()

        val noOps = Scope(callRules = listOf(recordingRule("empty", statements = emptyList(), ui = emptyList())))
        check(adaptCall(numberCall, plain, Scope(), CallContext.VALUE) { EtsTypes.NUMBER } == null)
        check(adaptCall(numberCall, plain, Scope(), CallContext.STATEMENT) { EtsTypes.NUMBER } == null)
        check(adaptCall(unitCall, plain, Scope(), CallContext.UI) == null)

        fun rejectedAdaptation(call: IrCall, scope: Scope, context: CallContext,
            expectedTargetType: (() -> EtsType)?, message: String) {
            val failure = runCatching {
                adaptCall(call, dispatch, scope, context, expectedTargetType)
            }.exceptionOrNull()
            check(failure is Unsupported && failure.diagnostic.message.contains(message)) { "Expected $message; got $failure" }
            check(failure.diagnostic.source == plain.source(call))
            check(failure.diagnostic.source.file == args[0] && failure.diagnostic.source.start >= 0)
        }
        val wrong = Scope(callRules = listOf(CallRule { call, language, _ ->
            EtsLiteral("wrong", EtsTypes.STRING, language.source(call))
        }))
        rejectedAdaptation(numberCall, wrong, CallContext.VALUE, { EtsTypes.NUMBER }, "Invalid call adapter result")
        rejectedAdaptation(numberCall, wrong, CallContext.STATEMENT, { EtsTypes.NUMBER }, "Invalid call adapter result")
        rejectedAdaptation(numberCall, Scope(), CallContext.VALUE, { EtsTypes.STRING }, "Invalid call adapter result")
        rejectedAdaptation(unitCall, voidOnly, CallContext.VALUE, { EtsTypes.VOID },
            "Void call adapter result requires statement consumption")
        rejectedAdaptation(numberCall, onlyUi, CallContext.UI, null, "UI call adapter requires kotlin.Unit")
        rejectedAdaptation(numberCall, noOps, CallContext.STATEMENT, { EtsTypes.NUMBER },
            "Empty statement adapter result")
        rejectedAdaptation(unitCall, noOps, CallContext.UI, null, "Empty UI adapter result")
        trace.clear()
        rejects("directEffect", Scope(callRules = listOf(badRule)), "Invalid call adapter result", plain)
        rejects("directEffect", Scope(), "Invalid call adapter result", LanguageLowering(diagnostics, listOf(badRule)))
        check(trace.isEmpty())
        println("PASS shared value/statement/UI dispatch, expected target checks, void/effect separation and source-linked invalid consumption")
    }
    check(runCatching { borrowed!!.module }.exceptionOrNull() is IllegalStateException)
    check(runCatching { borrowed!!.bodies }.exceptionOrNull() is IllegalStateException)
    println("PASS borrowed frontend session, real cross-file body and absent binary body")
}
