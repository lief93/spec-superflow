package ui.test

import dev.ets.*
import java.io.File

fun main(args: Array<String>) {
    val file = args[1]
    val program = withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], file)) { module ->
        val diagnostics = DiagnosticSink()
        val backend = EtsBackend(diagnostics, listOf(StandardLibraryRules()))
        backend.validateSource(module)
        ComposeLowering(backend.language, diagnostics).lower(module, "basiccontrols.BasicControls")
    }
    EtsValidator().validate(program)
    val nodes = mutableListOf<EtsNode>()
    program.files.flatMap { it.declarations }.forEach { walkEts(it, nodes::add) }
    fun elements(name: String) = nodes.filterIsInstance<EtsUiElement>().filter {
        (it.call.callee as? EtsReference)?.symbol?.name == name
    }
    fun EtsUiElement.attr(name: String) = attributes.single { (it.callee as? EtsReference)?.symbol?.name == name }.arguments.single()
    check(elements("Text").single().attr("maxLines").let { it is EtsLiteral && it.value == 2 })
    check(elements("Text").single().call.arguments.single() is EtsConditional)
    val dividers = elements("Divider")
    check(dividers.size == 2)
    check(dividers[0].attr("vertical").let { it is EtsLiteral && it.value == false })
    check(dividers[0].attr("strokeWidth").let { it is EtsReference && it.symbol.name == "line" })
    check(dividers[0].attr("color").let { it is EtsLiteral && it.value == 0xFFFF0000L })
    check(dividers[1].attr("vertical").let { it is EtsLiteral && it.value == true })
    check(dividers[1].attr("strokeWidth").let { it is EtsLiteral && it.value == 3 })
    val checkbox = elements("Checkbox").single()
    check(checkbox.attr("select").let { it is EtsMember && it.name == "selected" })
    val toggle = elements("Toggle").single()
    check((toggle.call.arguments.single() as EtsObject).fields["isOn"].let { it is EtsMember && it.name == "selected" })
    val callbacks = listOf(checkbox, toggle).map {
        check(it.attr("enabled").let { it is EtsReference && it.symbol.name == "enabled" })
        val callback = it.attr("onChange") as EtsLambda
        check(callback.parameters.single().symbol.type == EtsTypes.BOOLEAN)
        check(callback.returnType == EtsTypes.VOID)
        callback
    }
    check(callbacks.map { it.parameters.single().symbol.name } == listOf("next", "it"))
    val printer = EtsPrinter()
    val output = File(args[2]).apply { mkdirs() }
    File(output, "BasicControls.ets").writeText(printer.program(program))
    callbacks.forEachIndexed { i, callback -> File(output, "callback$i.ts").writeText("export const callback = " + printer.expression(callback) + ";\n") }
    println("PASS official Compose IR -> typed target: text, divider orientation/dimensions, shared Boolean state and callbacks")
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[3])) { module ->
        val cases = mapOf(
            "NullCheckbox" to "non-null (Boolean)",
            "NullSwitch" to "non-null (Boolean)",
            "StyledCheckbox" to "argument: colors",
            "SlottedSwitch" to "argument: thumbContent",
            "StyledBasicText" to "argument: style",
            "AnnotatedBasicText" to "AnnotatedString",
            "EffectfulThickness" to "stable thickness",
        )
        for ((entry, reason) in cases) {
            val diagnostics = DiagnosticSink()
            val backend = EtsBackend(diagnostics, listOf(StandardLibraryRules()))
            val failure = runCatching {
                ComposeLowering(backend.language, diagnostics).lower(module, "basiccontrols.$entry")
            }.exceptionOrNull()
            check(failure is Unsupported && reason in failure.message.orEmpty()) { "$entry: $failure" }
            val source = failure.diagnostic.source
            check(source.file == args[3] && source.start >= 0 && source.end > source.start)
        }
        println("PASS source-linked rejection: nullable selection callbacks, unsupported styles/slots, rich text and effectful thickness")
    }
}
