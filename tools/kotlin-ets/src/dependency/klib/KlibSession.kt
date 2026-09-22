@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.dependency.klib

import dev.ets.*
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.ir.util.fileOrNull
import org.jetbrains.kotlin.backend.common.IrModuleInfo
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.util.SymbolTable
import org.jetbrains.kotlin.ir.backend.js.lower.serialization.ir.JsIrLinker

/**
 * Borrowed official KLIB IR. Valid only inside [withKlibModules]. Callers must not
 * retain fragments, the linker, or the symbol table after the session closes.
 * Translated modules keep their original IrModuleFragment identity; this is not a
 * combined fake module.
 */
class KlibSession internal constructor(
    val modules: List<IrModuleFragment>,
    val loaded: IrModuleInfo,
    val selection: KlibModuleSelection,
    internal val configuration: CompilerConfiguration,
    internal val libraryLocations: Map<IrModuleFragment, String>,
) {
    private var active = true
    private var lowered = false
    internal fun checkActive() = check(active) { "KLIB session is closed" }

    val linker: JsIrLinker get() {
        checkActive()
        return loaded.deserializer as JsIrLinker
    }
    val symbolTable: SymbolTable get() {
        checkActive()
        return loaded.symbolTable
    }
    val allDependencies: List<IrModuleFragment> get() {
        checkActive()
        return loaded.allDependencies
    }

    fun linkedModules(): List<IrModuleFragment> {
        checkActive()
        return modules
    }

    /** Resolves serialized bodies by canonical symbol across every linked KLIB. */
    fun bodies(): FunctionBodies {
        checkActive()
        return FunctionBodies { symbol ->
            checkActive()
            when {
                !symbol.isBound -> FunctionBody.Unavailable(FunctionBody.Reason.UNBOUND_SYMBOL)
                symbol.owner.isExternal -> FunctionBody.Unavailable(FunctionBody.Reason.EXTERNAL_DECLARATION)
                else -> {
                    val function = symbol.owner
                    val file = function.fileOrNull
                    val location = libraryLocations[file?.module]
                    when {
                        location == null -> FunctionBody.Unavailable(FunctionBody.Reason.OUTSIDE_MODULE)
                        function.body == null -> FunctionBody.Unavailable(FunctionBody.Reason.NO_BODY)
                        else -> FunctionBody.Available(function, function.body!!,
                            SourceSpan(file!!.fileEntry.name, function.startOffset, function.endOffset),
                            FunctionBody.Origin.SerializedKlibIr(location, file.module.name.asString()))
                    }
                }
            }
        }
    }

    internal fun beginLowering() {
        checkActive()
        check(!lowered) { "KLIB session has already been lowered" }
        lowered = true
    }

    internal fun close() {
        active = false
    }
}
