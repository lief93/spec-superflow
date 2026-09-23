@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.examples

import dev.ets.*
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.util.render

class ExampleProjectInputsModule : AdapterModule {
    override val id = "example.project-inputs"

    private val provider = AdapterCallIdentity(
        symbol = "demo.projectinputs.projectInput",
        typeParameters = 1,
        parameters = listOf("kotlin.String"),
        returnType = "T of demo.projectinputs.projectInput",
    )
    private val dependency = AdapterCallIdentity(
        symbol = "demo.projectinputs.targetDependency",
        typeParameters = 0,
        parameters = listOf("kotlin.String"),
        returnType = "kotlin.String",
    )
    private val component = AdapterCallIdentity(
        symbol = "demo.projectinputs.ProjectCard",
        typeParameters = 0,
        parameters = listOf("kotlin.String", "@[Composable] kotlin.Function0<kotlin.Unit>"),
        returnType = "kotlin.Unit",
    )
    private val key = AdapterTargetParameter("key", EtsTypes.STRING)
    private val name = AdapterTargetParameter("name", EtsTypes.STRING)
    private val title = AdapterTargetParameter("title", EtsTypes.STRING)
    private val resource = EtsNamedType("Resource", external = true)

    private fun input(sourceType: String, targetType: EtsType, kind: AdapterInputKind, targetId: String) =
        AdapterProjectInput(provider, sourceType, targetType, kind = kind,
            parameters = listOf(key), targetId = targetId)

    override val projectInputs = listOf(
        input("demo.projectinputs.ProjectToken", EtsTypes.BOOLEAN, AdapterInputKind.TOKEN, "project-input.token"),
        input("demo.projectinputs.ProjectColor", EtsTypes.NUMBER, AdapterInputKind.COLOR, "project-input.color"),
        input("demo.projectinputs.ProjectFont", EtsTypes.STRING, AdapterInputKind.FONT, "project-input.font"),
        input("demo.projectinputs.ProjectDimension", EtsTypes.NUMBER, AdapterInputKind.DIMENSION, "project-input.dimension"),
        input("demo.projectinputs.ProjectString", EtsTypes.STRING, AdapterInputKind.STRING_RESOURCE, "project-input.string"),
        input("demo.projectinputs.ProjectImage", resource, AdapterInputKind.IMAGE_RESOURCE, "project-input.image"),
        AdapterProjectInput(dependency, "kotlin.String", EtsTypes.STRING,
            kind = AdapterInputKind.TARGET_DEPENDENCY, parameters = listOf(name), targetId = "project-input.dependency"),
        AdapterProjectInput(component, "kotlin.Unit", EtsTypes.VOID,
            kind = AdapterInputKind.BUSINESS_COMPONENT, consumption = AdapterInputConsumption.UI,
            parameters = listOf(title), contentSlot = AdapterContentSlot("content")),
    )

    override val sourceTypes = setOf(
        "demo.projectinputs.ProjectToken",
        "demo.projectinputs.ProjectColor",
        "demo.projectinputs.ProjectFont",
        "demo.projectinputs.ProjectDimension",
        "demo.projectinputs.ProjectString",
        "demo.projectinputs.ProjectImage",
    )

    override val targetCalls = listOf(
        AdapterTargetCall("project-input.token", "projectToken", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.BOOLEAN)),
        AdapterTargetCall("project-input.color", "projectColor", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER)),
        AdapterTargetCall("project-input.font", "projectFont", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.STRING)),
        AdapterTargetCall("project-input.dimension", "projectDimension", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.NUMBER)),
        AdapterTargetCall("project-input.string", "projectString", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.STRING)),
        AdapterTargetCall("project-input.image", "projectImage", EtsFunctionType(listOf(EtsTypes.STRING), resource)),
        AdapterTargetCall("project-input.dependency", "projectDependency", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.STRING)),
        AdapterTargetCall("project-input.column", "Column", EtsFunctionType(emptyList(), EtsTypes.VOID)),
        AdapterTargetCall("project-input.text", "Text", EtsFunctionType(listOf(EtsTypes.STRING), EtsTypes.VOID)),
    )

    override val imports = listOf(
        EtsImport("./ProjectInputsHost", "projectToken"),
        EtsImport("./ProjectInputsHost", "projectColor"),
        EtsImport("./ProjectInputsHost", "projectFont"),
        EtsImport("./ProjectInputsHost", "projectDimension"),
        EtsImport("./ProjectInputsHost", "projectString"),
        EtsImport("./ProjectInputsHost", "projectImage"),
        EtsImport("./ProjectInputsHost", "projectDependency"),
    )

    private val targetTypes = mapOf(
        "demo.projectinputs.ProjectToken" to EtsTypes.BOOLEAN,
        "demo.projectinputs.ProjectColor" to EtsTypes.NUMBER,
        "demo.projectinputs.ProjectFont" to EtsTypes.STRING,
        "demo.projectinputs.ProjectDimension" to EtsTypes.NUMBER,
        "demo.projectinputs.ProjectString" to EtsTypes.STRING,
        "demo.projectinputs.ProjectImage" to resource,
    )

    override fun create(target: AdapterTargetApi, ui: AdapterUiServices?): CallRule = object : CallRule {
        override fun mapType(type: org.jetbrains.kotlin.ir.types.IrType, language: Language): EtsType? =
            type.classOrNull?.owner?.let(::symbolName)?.let(targetTypes::get)

        override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
            val symbol = symbolName(call.symbol.owner)
            val id = when (symbol) {
                provider.symbol -> when (call.type.render()) {
                    "demo.projectinputs.ProjectToken" -> "project-input.token"
                    "demo.projectinputs.ProjectColor" -> "project-input.color"
                    "demo.projectinputs.ProjectFont" -> "project-input.font"
                    "demo.projectinputs.ProjectDimension" -> "project-input.dimension"
                    "demo.projectinputs.ProjectString" -> "project-input.string"
                    "demo.projectinputs.ProjectImage" -> "project-input.image"
                    else -> return null
                }
                dependency.symbol -> "project-input.dependency"
                else -> return null
            }
            val parameter = if (symbol == provider.symbol) "key" else "name"
            val value = argument(call, parameter) ?: return null
            return target.call(id, listOf(language.expression(value, scope)), language.source(call))
        }

        override fun lowerUi(call: IrCall, language: Language, scope: Scope): List<EtsStatement>? {
            if (ui == null || symbolName(call.symbol.owner) != component.symbol) return null
            val title = argument(call, "title") ?: return null
            val content = argument(call, "content") ?: return null
            val source = language.source(call)
            val heading = EtsUiElement(target.call("project-input.text",
                listOf(language.expression(title, scope)), source))
            return listOf(EtsUiElement(target.call("project-input.column", emptyList(), source),
                listOf(heading) + ui.content(content, scope)))
        }
    }
}
