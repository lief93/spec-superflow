@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.pipeline.ComposeWidgetPipeline
import dev.ets.widgets.*
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgetlazy.LazyListProfile" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val plan = ComposeStateLowering(backend.language, sink).lower(entry, Scope(), "LazyListProfile")
        val model = ComposeWidgetAdapter(backend.language, sink, plan.pagers, plan.scrolls)
            .lower(entry, plan.scope, plan.handledStatements)
        val root = model.widgets.single() as Widget.Column<EtsExpression, SourceSpan>
        check(root.children.widgets.size == 2)
        val column = root.children.widgets[0] as Widget.LazyList<EtsExpression, SourceSpan>
        val row = root.children.widgets[1] as Widget.LazyList<EtsExpression, SourceSpan>
        check(column.axis == WidgetScrollAxis.VERTICAL && row.axis == WidgetScrollAxis.HORIZONTAL)
        check((column.enabled as EtsLiteral).value == false && (row.enabled as EtsLiteral).value == true)
        check(column.slots.size == 4 && row.slots.size == 1)
        check(column.slots[0] is LazyListSlot.Item)
        val indexed = column.slots[1] as LazyListSlot.Items<EtsExpression, SourceSpan>
        val count = column.slots[2] as LazyListSlot.Items<EtsExpression, SourceSpan>
        val empty = column.slots[3] as LazyListSlot.Items<EtsExpression, SourceSpan>
        check(indexed.data is LazyListData.Values && count.data is LazyListData.Count &&
            empty.data is LazyListData.Values)
        check((indexed.item as EtsReference).type == EtsTypes.STRING)
        check((indexed.index as EtsReference).type == EtsTypes.NUMBER)
        check(indexed.key?.type == EtsTypes.STRING && count.key?.type == EtsTypes.NUMBER)
        check(((empty.data as LazyListData.Values).values as EtsArray).elements.isEmpty())

        val target = HarmonyWidgetBackend().lower(model)
        fun name(element: EtsUiElement) = (element.call.callee as EtsReference).symbol.name
        val targetRoot = target.single() as EtsUiElement
        check(name(targetRoot) == "Column")
        val targetColumn = targetRoot.children!![0] as EtsUiElement
        val targetRow = targetRoot.children!![1] as EtsUiElement
        check(name(targetColumn) == "List" && name(targetRow) == "List")
        check((targetColumn.attributes[0].arguments.single() as EtsMember).name == "Vertical")
        check((targetRow.attributes[0].arguments.single() as EtsMember).name == "Horizontal")
        check(targetColumn.children!!.first() is EtsUiElement)
        val lazy = targetColumn.children!!.drop(1).filterIsInstance<EtsUiLazyForEach>()
        check(lazy.size == 3 && targetRow.children!!.single() is EtsUiLazyForEach)
        check(lazy.all { it.body.single().let { body -> body is EtsUiElement && name(body) == "ListItem" } })
        check(lazy.map { it.item.symbol.type } == listOf(EtsTypes.STRING, EtsTypes.NUMBER, EtsTypes.STRING))
        check(lazy.all { it.index.symbol.type == EtsTypes.NUMBER })
        check(lazy.map { it.key?.returnType } == listOf(EtsTypes.STRING, EtsTypes.STRING, EtsTypes.STRING))

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetlazy.LazyListProfile")
        File(output, "LazyListProfile.ets").writeText(code)
        check("class __etsLazyArrayDataSource<T> implements IDataSource" in code)
        check("function __etsLazyIndices(count: number): Array<number>" in code)
        check("List() {" in code && "LazyForEach(" in code && "ListItem() {" in code)
        check(".listDirection(Axis.Vertical)" in code && ".listDirection(Axis.Horizontal)" in code)
        check(".enableScrollInteraction(false)" in code && ".enableScrollInteraction(true)" in code)
        check("new __etsLazyArrayDataSource<string>([\"Ada\", \"Lin\"] as Array<string>)" in code)
        check("new __etsLazyArrayDataSource<number>(__etsLazyIndices(3))" in code)
        check("new __etsLazyArrayDataSource<string>([] as Array<string>)" in code)
        check("Text(\"\" + index + \":\" + item)" in code)
        check("this.__etsState_selected = item;" in code)

        val expected = linkedMapOf(
            "StickyHeaderList" to "Unsupported lazy list DSL",
            "ContentTypeList" to "contentType",
            "StatefulList" to "state and prefetch strategies",
            "ReverseList" to "argument: reverseLayout",
            "UnstableKeyList" to "stable String or Int",
            "AnimatedItemList" to "animateItem",
            "LazyGrid" to "Unsupported resolved widget API",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                    .compile(module, "widgetlazy.$name")
                error("Accepted unsupported lazy-list fixture $name")
            } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/LazyListUnsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "lazy-list-diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
    }
    println("PASS official LazyColumn/LazyRow -> neutral LazyList slots -> typed List/LazyForEach")
}
