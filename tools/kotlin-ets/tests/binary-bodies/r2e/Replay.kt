@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.r2e

import dev.ets.*
import java.io.File
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

// The caller supplies the stateless receiver implementation; no binary class is fabricated.
private class ReceiverTypes : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val name = type.classOrNull?.owner?.fqNameWhenAvailable?.asString()
        return when (name) {
            "memberbinary.FinalMember", "memberbinary.PeerMember" ->
                EtsNamedType(name.substringAfterLast('.'), symbolId = "test-receiver:$name", external = true)
            else -> null
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? = null
}

fun main(args: Array<String>) {
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { session ->
        val backend = EtsBackend(DiagnosticSink(), listOf(ReceiverTypes(), StandardLibraryRules()))
        val program = backend.lower(session.module).copy(imports = listOf(
            EtsImport("./Receivers", "FinalMember"), EtsImport("./Receivers", "PeerMember")))
        File(args[2]).writeText(emitEtsProgram(program, StandardLibraryRuntime))
    }
}
