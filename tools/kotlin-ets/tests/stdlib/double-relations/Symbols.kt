@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.tests.doublerelations

import dev.ets.*
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*

fun main(args: Array<String>) = withKotlinFrontend(args.toList()) { frontend ->
    val calls = mutableListOf<Pair<String, IrCall>>()
    val operators = mapOf("kotlin.internal.ir.less" to "<", "kotlin.internal.ir.lessOrEqual" to "<=",
        "kotlin.internal.ir.greater" to ">", "kotlin.internal.ir.greaterOrEqual" to ">=")
    frontend.module.files.forEach { file -> file.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
        override fun visitCall(expression: IrCall) {
            val name = symbolName(expression.symbol.owner)
            if (name in operators || file.fileEntry.name.endsWith("Rejected.kt"))
                calls.add(file.fileEntry.name to expression)
            expression.acceptChildrenVoid(this)
        }
    }) }
    val rules = StandardLibraryRules()
    var accepted = 0
    var declined = 0
    var mutations = 0
    for ((file, call) in calls) {
        val owner = call.symbol.owner
        println("ACTUAL ${symbolName(owner)} ${owner.render()} origin=${owner.origin}")
        val language = RelationLanguage(file)
        val result = rules.lower(call, language, Scope())
        if (file.endsWith("Rejected.kt")) {
            check(result == null && language.inputs.isEmpty()) { "Accepted excluded relation ${owner.render()}" }
            declined++
            continue
        }
        check(result is EtsBinary && result.operator == operators.getValue(symbolName(owner))) { "Missing exact Double relation" }
        check(result.type == EtsTypes.BOOLEAN)
        check(language.inputs.size == 2 && language.inputs[0] === call.getValueArgument(0) && language.inputs[1] === call.getValueArgument(1))
        val program = EtsProgram(listOf(EtsFile(file, listOf(EtsFunction("compare", language.symbols.map(::EtsParameter),
            EtsTypes.BOOLEAN, listOf(EtsReturn(result, result.source)), language.source(call))))))
        EtsValidator().validate(program)
        check(StandardLibraryRuntime.declarations(program).isEmpty())
        accepted++
        val left = call.getValueArgument(0)!!
        val right = call.getValueArgument(1)!!
        val leftType = left.type
        val rightType = right.type
        val returnType = call.type
        val declaredResult = owner.returnType
        val declaredLeft = owner.valueParameters[0].type
        val declaredRight = owner.valueParameters[1].type
        val origin = owner.origin
        val intType = calls.first { it.second.type.isInt() }.second.type
        fun reject(label: String, change: () -> Unit, restore: () -> Unit) {
            try {
                change()
                val probe = RelationLanguage(file)
                check(rules.lower(call, probe, Scope()) == null && probe.inputs.isEmpty()) { "Accepted malformed $label" }
                mutations++
            } finally { restore() }
        }
        reject("dispatch", { call.insertDispatchReceiver(left) }, { call.removeDispatchReceiver() })
        reject("extension", { call.insertExtensionReceiver(left) }, { call.removeExtensionReceiver() })
        reject("super", { call.superQualifierSymbol = leftType.classOrNull }, { call.superQualifierSymbol = null })
        reject("missing operand", { call.putValueArgument(1, null) }, { call.putValueArgument(1, right) })
        reject("nullable left", { left.type = leftType.makeNullable() }, { left.type = leftType })
        reject("nullable right", { right.type = rightType.makeNullable() }, { right.type = rightType })
        reject("mixed left", { left.type = intType }, { left.type = leftType })
        reject("mixed right", { right.type = intType }, { right.type = rightType })
        reject("wrong result", { call.type = leftType }, { call.type = returnType })
        reject("nullable result", { call.type = returnType.makeNullable() }, { call.type = returnType })
        reject("declared result", { owner.returnType = leftType }, { owner.returnType = declaredResult })
        reject("declared mixed left", { owner.valueParameters[0].type = intType }, { owner.valueParameters[0].type = declaredLeft })
        reject("declared nullable right", { owner.valueParameters[1].type = rightType.makeNullable() }, { owner.valueParameters[1].type = declaredRight })
        reject("source origin", { owner.origin = IrDeclarationOrigin.DEFINED }, { owner.origin = origin })
    }
    check(accepted == 4 && declined == 6 && mutations == 56) { "$accepted/$declined/$mutations" }
    println("PASS four actual Double relations, six excluded APIs, 56 malformed signatures before children; no runtime")
}

private class RelationLanguage(private val file: String) : Language {
    val inputs = mutableListOf<IrExpression>()
    val symbols = mutableListOf<EtsSymbol>()
    override fun source(element: IrElement) = SourceSpan(file, element.startOffset, element.endOffset)
    override fun type(type: IrType): EtsType = when {
        type.isDouble() -> EtsTypes.NUMBER
        type.isBoolean() -> EtsTypes.BOOLEAN
        else -> error(type.render())
    }
    override fun expression(expression: IrExpression, scope: Scope): EtsExpression {
        inputs.add(expression)
        check(expression.type.isDouble())
        val name = "operand${symbols.size}"
        val symbol = EtsSymbol(name, name, EtsTypes.NUMBER, source(expression))
        symbols.add(symbol)
        return EtsReference(symbol)
    }
    override fun statements(body: IrBody, scope: Scope): List<EtsStatement> = error("Not a body probe")
    override fun function(function: IrSimpleFunction, scope: Scope): EtsFunction = error("Not a function probe")
    override fun clazz(declaration: IrClass): EtsClass = error("Not a class probe")
}
