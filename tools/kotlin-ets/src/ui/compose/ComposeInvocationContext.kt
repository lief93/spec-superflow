package dev.ets.compose

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.IrModuleFragment
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction

/** Public pipeline seam; concrete Compose context types remain compiler-owned. */
class ComposeInvocationContext(private val language: Language) {
    fun initialize(module: IrModuleFragment, entry: IrSimpleFunction, scope: Scope): Boolean {
        if (language.callRules.none { it is ComposeTextStyleRule } ||
            language.callRules.none { it is ComposeTypographyRule } ||
            language.callRules.none { it is ComposeMaterialThemeValueRule }) return false
        if (!requiresMaterialContext(module)) return false
        val source = language.source(entry)
        val shapes = language.callRules.filterIsInstance<ComposeShapeRule>().singleOrNull()
        scope.ambientValues[MATERIAL_CONTEXT] =
            defaultMaterialContext(source, shapes?.initialShapes(source) ?: defaultMaterialShapes(source))
        return true
    }

    fun bindComponent(entry: IrSimpleFunction, scope: Scope): EtsField? {
        val initial = scope.ambientValues[MATERIAL_CONTEXT] ?: return null
        val source = language.source(entry)
        val owner = etsClassSymbol(entry.name.asString(), source).type as EtsNamedType
        val field = EtsField(EtsSymbol(
            "compose-context:${source.file}:${entry.startOffset}:component:material",
            "__etsMaterialContext", materialContextType, source), initial, readonly = true)
        val self = EtsReference(EtsSymbol(
            "compose-context:${source.file}:${entry.startOffset}:component:this",
            "this", owner, source, external = true))
        scope.ambientValues[MATERIAL_CONTEXT] = EtsMember(self, field.symbol.name,
            field.symbol.type, source, field.symbol.id)
        return field
    }
}
