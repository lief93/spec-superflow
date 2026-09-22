package dev.ets

import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0], args[1])) { module ->
        val sink = DiagnosticSink()
        val program = EtsBackend(sink, listOf(StandardLibraryRules())).lower(module)
        EtsValidator().validate(program)
        val source = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
            .single { it.fqNameWhenAvailable?.asString() == "callbackstate.callbackState" }
        val function = program.files.flatMap { it.declarations }.filterIsInstance<EtsFunction>()
            .single { it.source.file == sourceFile(source)?.fileEntry?.name && it.name == "callbackState" }
        val nodes = mutableListOf<EtsNode>()
        walkEts(function, nodes::add)
        val callback = nodes.filterIsInstance<EtsLambda>()
            .single { it.parameters.singleOrNull()?.symbol?.name == "delta" }
        val callbackNodes = mutableListOf<EtsNode>()
        walkEts(callback, callbackNodes::add)
        val assignments = callbackNodes.filterIsInstance<EtsAssignment>()
        fun assignedName(assignment: EtsAssignment) = when (val target = assignment.target) {
            is EtsReference -> target.symbol.name
            is EtsMember -> target.name
            else -> null
        }
        val assignedState = assignments.mapNotNull(::assignedName).toSet()
        check("local" in assignedState && assignedState.containsAll(setOf("total", "enabled"))) {
            "Callback state assignments did not remain typed: $assignedState"
        }
        val condition = callbackNodes.filterIsInstance<EtsIf>().single().branches.first().condition
            ?: error("State branch lost its condition")
        val conditionNodes = mutableListOf<EtsNode>()
        walkEts(condition, conditionNodes::add)
        val conditionMembers = conditionNodes.filterIsInstance<EtsMember>().map { it.name }.toSet()
        val conditionReferences = conditionNodes.filterIsInstance<EtsReference>().map { it.symbol.name }.toSet()
        check("enabled" in conditionMembers && ("local" in conditionReferences || "value" in conditionMembers)) {
            "State reads did not remain typed in the condition: members=$conditionMembers references=$conditionReferences"
        }
        val statements = callback.body
        val branchIndex = statements.indexOfFirst { statement ->
            var found = false
            walkEts(statement) { if (it is EtsIf) found = true }
            found
        }
        check(branchIndex > 0) { "Callback condition did not remain ordered after its updates" }
        val writesBeforeBranch = statements.take(branchIndex).flatMap { statement ->
            val names = mutableListOf<String>()
            walkEts(statement) { node ->
                if (node is EtsAssignment) assignedName(node)?.let(names::add)
            }
            names
        }.toSet()
        check("local" in writesBeforeBranch && writesBeforeBranch.containsAll(setOf("total", "enabled"))) {
            "Callback writes did not remain ordered before the condition: $writesBeforeBranch"
        }
        check(callbackNodes.none { it is EtsUiElement || it is EtsUiComponent || it is EtsUiForEach })
        println("PASS typed callback state: captured local/property assignments and subsequent condition reads remain ETS IR")
    }
}
