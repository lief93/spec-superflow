@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrValueParameter
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrConst
import org.jetbrains.kotlin.ir.expressions.IrConstructorCall
import org.jetbrains.kotlin.ir.expressions.IrGetObjectValue
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull

private val navigationSource = SourceSpan("EtsNavigation.kt", -1, -1)
private val routerType = EtsNamedType("router", external = true)
private val routerSymbol = EtsSymbol("arkui:router", "router", routerType, navigationSource, true)
private val namedRouteOptionsType = EtsRecordType("NamedRouterOptions", mapOf("name" to EtsTypes.STRING))
private val pushNamedRouteType = EtsFunctionType(listOf(namedRouteOptionsType), EtsTypes.VOID)

/** Android Navigation calls become the equivalent ArkUI named-route operation.
 *  Route registration remains a target-project concern; object route identity is preserved by name. */
internal class ComposeNavigationRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? {
        val name = type.classOrNull?.owner?.let(::symbolName) ?: return null
        return if (name in setOf("androidx.navigation.NavController", "androidx.navigation.NavHostController"))
            EtsTypes.OBJECT else null
    }

    override fun omittedArgumentResolution(call: IrCall, parameter: IrValueParameter): String? {
        if (!isNavigate(call)) return null
        return if (parameter.name.asString() in setOf("navOptions", "navigatorExtras"))
            "target_platform_default" else null
    }

    override fun ownsSourceArgumentDependency(call: IrCall, index: Int): Boolean {
        if (!isNavigate(call) || index != 0) return false
        return when (call.getValueArgument(index)) {
            is IrGetObjectValue, is IrConstructorCall, is IrConst -> true
            else -> false
        }
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        if (!isNavigate(call)) return null
        val route = call.getValueArgument(0)
            ?: throw Unsupported(Diagnostic("UNSUPPORTED", "Navigation navigate requires a route", language.source(call)))
        val name = when (route) {
            is IrGetObjectValue -> route.symbol.owner.name.asString()
            is IrConstructorCall -> (route.symbol.owner.parent as? org.jetbrains.kotlin.ir.declarations.IrClass)
                ?.name?.asString()
            is IrConst -> route.value as? String
            else -> null
        } ?: throw Unsupported(Diagnostic("UNSUPPORTED",
            "Navigation route requires a typed route object, route constructor, or String", language.source(route)))
        val at = language.source(call)
        val options = EtsObject(linkedMapOf("name" to EtsLiteral(name, EtsTypes.STRING, at)),
            namedRouteOptionsType, at)
        return EtsCall(EtsMember(EtsReference(routerSymbol, at), "pushNamedRoute", pushNamedRouteType, at),
            listOf(options), EtsTypes.VOID, at)
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> {
        var used = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id == routerSymbol.id) used = true
        } } }
        return if (used) listOf(EtsImport("@kit.ArkUI", "router")) else emptyList()
    }

    private fun isNavigate(call: IrCall): Boolean {
        if (sourceFile(call.symbol.owner) != null) return false
        return symbolName(call.symbol.owner) in setOf(
            "androidx.navigation.NavController.navigate",
            "androidx.navigation.NavHostController.navigate",
        )
    }
}
