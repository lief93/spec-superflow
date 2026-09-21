package dev.ets.dependency.klib

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
) {
    private var active = true
    private fun checkActive() = check(active) { "KLIB session is closed" }

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

    internal fun close() {
        active = false
    }
}
