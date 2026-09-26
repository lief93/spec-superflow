@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.intdouble

import dev.ets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) = withKotlinFrontend(args.toList()) { frontend ->
    val calls = mutableListOf<Pair<String, IrCall>>()
    frontend.module.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
        override fun visitCall(expression: IrCall) {
            if (expression.symbol.owner.name.asString() == "toDouble") calls.add(file.fileEntry.name to expression)
            expression.acceptChildrenVoid(this)
        }
    }) }
    val rules = StandardLibraryRules()
    var accepted = 0
    var declined = 0
    var promoted = 0
    var mutations = 0
    for ((file, call) in calls) {
        val owner = call.symbol.owner
        val language = ConversionLanguage(file)
        println("ACTUAL ${symbolName(owner)} ${owner.render()} origin=${owner.origin} fake=${owner.isFakeOverride} dispatch=${owner.dispatchReceiverParameter?.type?.render()}")
        val result = rules.lower(call, language, Scope())
        if (file.endsWith("Rejected.kt")) {
            if (symbolName(owner) in setOf("kotlin.Float.toDouble", "kotlin.Double.toDouble")) {
                check(result is EtsReference && language.inputs.single() === call.dispatchReceiver)
                promoted++
                continue
            }
            check(result == null && language.inputs.isEmpty()) { "Accepted unapproved conversion ${symbolName(owner)}" }
            declined++
            continue
        }
        checkNotNull(result) { "Missing exact Int.toDouble adapter" }
        check(result.type == EtsTypes.NUMBER)
        check(language.inputs.size == 1 && language.inputs.single() === call.dispatchReceiver)
        val program = EtsProgram(listOf(EtsFile(file, listOf(EtsFunction("convert", listOf(EtsParameter(language.symbol)),
            EtsTypes.NUMBER, listOf(EtsReturn(result, result.source)), language.source(call))))))
        EtsValidator().validate(program)
        check(StandardLibraryRuntime.declarations(program).isEmpty()) { "Identity conversion must add no runtime" }
        val references = mutableListOf<EtsReference>()
        walkEts(result) { if (it is EtsReference) references.add(it) }
        check(references.size == 1 && references.single().symbol == language.symbol)
        accepted++
        if (accepted != 1) continue
        val receiver = call.dispatchReceiver!!
        val receiverType = receiver.type
        val returnType = call.type
        val declaredResult = owner.returnType
        val declaredReceiver = owner.dispatchReceiverParameter!!
        val declaredReceiverType = declaredReceiver.type
        val origin = owner.origin
        fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
            try {
                change()
                val probe = ConversionLanguage(file)
                check(rules.lower(call, probe, Scope()) == null && probe.inputs.isEmpty()) { "Accepted malformed $label" }
                println("REJECT $label before children")
                mutations++
            } finally { restore() }
        }
        reject("missing dispatch", { call.dispatchReceiver = null }, { call.dispatchReceiver = receiver })
        reject("extension dispatch", { call.insertExtensionReceiver(receiver) }, { call.removeExtensionReceiver() })
        reject("super dispatch", { call.superQualifierSymbol = receiverType.classOrNull }, { call.superQualifierSymbol = null })
        reject("nullable receiver", { receiver.type = receiverType.makeNullable() }, { receiver.type = receiverType })
        reject("wrong receiver", { receiver.type = returnType }, { receiver.type = receiverType })
        reject("nullable result", { call.type = returnType.makeNullable() }, { call.type = returnType })
        reject("wrong result", { call.type = receiverType }, { call.type = returnType })
        reject("declared result", { owner.returnType = receiverType }, { owner.returnType = declaredResult })
        reject("declared receiver", { declaredReceiver.type = returnType }, { declaredReceiver.type = declaredReceiverType })
        reject("declared nullable receiver", { declaredReceiver.type = receiverType.makeNullable() }, { declaredReceiver.type = declaredReceiverType })
        reject("source origin", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
        reject("declared nullable result", { owner.returnType = declaredResult.makeNullable() }, { owner.returnType = declaredResult })
    }
    check(accepted == 2 && promoted == 2 && declined == 3 && mutations == 12) { "$accepted/$promoted/$declined/$mutations" }
    println("PASS two Int.toDouble and two promoted floating conversions, three excluded families, 12 malformed signatures")
}

private class ConversionLanguage(private val file: String) : Language {
    val inputs = mutableListOf<IrExpression>()
    val symbol = EtsSymbol("conversion:receiver", "receiver", EtsTypes.NUMBER, SourceSpan(file, 0, 1))
    override fun source(element: IrElement) = SourceSpan(file, element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType = if (type.isInt() || type.isDouble()) EtsTypes.NUMBER else error(type.render())
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        inputs.add(expression)
        check(expression.type.isInt() || expression.type.isFloat() || expression.type.isDouble())
        return EtsReference(symbol, source(expression))
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Not a body probe")
    override fun function(function: IrSimpleFunction, scope: Scope,
        semantics: FunctionTargetSemantics): EtsFunction = error("Not a function probe")
    override fun clazz(declaration: IrClass): EtsClass = error("Not a class probe")
}
