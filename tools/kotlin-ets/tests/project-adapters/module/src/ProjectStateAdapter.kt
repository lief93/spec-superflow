@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.projectadapter

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.util.render

class ProjectStateAdapter : AdapterModule {
    override val id = "test.project-state"

    private val injected = AdapterCallIdentity(
        symbol = "projectdependency.injected",
        typeParameters = 1,
        parameters = emptyList(),
        returnType = "T of projectdependency.injected",
    )
    private val constructed = AdapterCallIdentity(
        symbol = "projectdependency.constructed",
        typeParameters = 1,
        parameters = emptyList(),
        returnType = "T of projectdependency.constructed",
    )
    private val local = AdapterCallIdentity(
        symbol = "projectconsumer.localState",
        typeParameters = 0,
        parameters = emptyList(),
        returnType = "projectconsumer.StateHolder",
    )
    private fun named(name: String) = EtsNamedType(name)

    override val projectCalls = listOf(
        AdapterProjectCall(injected, "projectconsumer.StateHolder", named("StateHolder")),
        AdapterProjectCall(injected, "projectconsumer.Box<projectconsumer.StateHolder>",
            named("Box").copy(arguments = listOf(named("StateHolder")))),
        AdapterProjectCall(constructed, "projectconsumer.ConstructedHolder", named("ConstructedHolder")),
        AdapterProjectCall(injected, "projectconsumer.WrongHolder", named("WrongHolder")),
        AdapterProjectCall(injected, "projectconsumer.VoidHolder", named("VoidHolder")),
        AdapterProjectCall(injected, "projectconsumer.ArgumentHolder", named("ArgumentHolder"), explicitArguments = 1),
        AdapterProjectCall(injected, "projectconsumer.ScopeHolder", named("ScopeHolder"), requiredScope = "project.screen"),
        AdapterProjectCall(local, "projectconsumer.StateHolder", named("StateHolder")),
    )
    override val targetValues = listOf(
        AdapterTargetValue("test.project-state.injected", "providedState", named("StateHolder")),
        AdapterTargetValue("test.project-state.box", "providedBox",
            named("Box").copy(arguments = listOf(named("StateHolder")))),
    )
    override val imports = listOf(
        EtsImport("./InjectionHost", "providedState"),
        EtsImport("./InjectionHost", "providedBox"),
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            val at = language.source(call)
            val type = language.type(call.type)
            return when (call.type.render()) {
                "projectconsumer.StateHolder" -> target.value("test.project-state.injected", type, at)
                "projectconsumer.Box<projectconsumer.StateHolder>" -> target.value("test.project-state.box", type, at)
                "projectconsumer.ConstructedHolder" -> EtsNew(type as EtsNamedType,
                    listOf(EtsLiteral("constructed", EtsTypes.STRING, at)), at)
                "projectconsumer.WrongHolder" -> EtsLiteral("wrong", EtsTypes.STRING, at)
                "projectconsumer.VoidHolder" -> EtsLiteral(null, EtsTypes.VOID, at)
                "projectconsumer.ArgumentHolder", "projectconsumer.ScopeHolder" ->
                    EtsNew(type as EtsNamedType, listOf(EtsLiteral("unreachable", EtsTypes.STRING, at)), at)
                else -> null
            }
        }
    }
}
