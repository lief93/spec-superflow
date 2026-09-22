package dev.ets.compose

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.IrClass
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.types.IrSimpleType
import org.jetbrains.kotlin.ir.types.IrTypeProjection
import org.jetbrains.kotlin.ir.types.classOrNull

/** Links source-owned object contracts used by a widget entry signature. */
class ComposeInputContracts(private val language: Language, private val diagnostics: DiagnosticSink) {
    fun lower(function: IrSimpleFunction): List<Pair<String, EtsClass>> {
        val classes = linkedSetOf<IrClass>()
        fun collect(type: org.jetbrains.kotlin.ir.types.IrType) {
            val simple = type as? IrSimpleType ?: return
            val owner = simple.classOrNull?.owner
            if (owner != null && sourceFile(owner) != null) classes += owner
            simple.arguments.forEach { argument -> (argument as? IrTypeProjection)?.type?.let(::collect) }
        }
        function.valueParameters.forEach { collect(it.type) }
        return classes.map { source ->
            val path = language.source(source).file
                ?: diagnostics.unsupported(source, "Widget input contract requires a source file")
            path to language.clazz(source).copy(exported = true)
        }
    }
}
