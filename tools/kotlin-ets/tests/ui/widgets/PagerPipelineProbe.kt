@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.widgettest

import dev.ets.*
import dev.ets.compose.ComposeStateLowering
import dev.ets.compose.ComposeWidgetAdapter
import dev.ets.harmony.HarmonyWidgetBackend
import dev.ets.pipeline.ComposeWidgetPipeline
import dev.ets.widgets.Widget
import java.io.File
import org.jetbrains.kotlin.ir.declarations.IrSimpleFunction
import org.jetbrains.kotlin.ir.util.fqNameWhenAvailable

fun main(args: Array<String>) {
    val output = File(args[1]).apply { mkdirs() }
    withKotlinModule(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(2)) { module ->
        val functions = module.files.flatMap { it.declarations }.filterIsInstance<IrSimpleFunction>()
        val entry = functions.single { it.fqNameWhenAvailable?.asString() == "widgetpager.PagerProfile" }
        val sink = DiagnosticSink()
        val backend = EtsBackend(sink, listOf(StandardLibraryRules()))
        val plan = ComposeStateLowering(backend.language, sink).lower(entry, Scope(), "PagerProfile")
        check(plan.fields.map { it.symbol.name to it.symbol.type } == listOf(
            "pager_currentPage" to EtsTypes.NUMBER,
            "pager_controller" to EtsNamedType("SwiperController")))
        check(plan.fields[0].state && plan.fields[0].visibility == EtsVisibility.PRIVATE)
        check(!plan.fields[1].state && plan.fields[1].visibility == EtsVisibility.PRIVATE)
        check((plan.fields[0].initializer as EtsLiteral).value == 1)
        check(plan.fields[1].initializer is EtsNew)
        val state = plan.pagers.values.single()
        check((state.pageCount as EtsLiteral).value == 3)

        val model = ComposeWidgetAdapter(backend.language, sink, plan.pagers)
            .lower(entry, plan.scope, plan.handledStatements)
        val pager = model.widgets.single() as Widget.Pager<EtsExpression, SourceSpan>
        check(pager.currentPage == state.currentPage && pager.controller == state.controller)
        check((pager.pageCount as EtsLiteral).value == 3)
        check(pager.pageContent.index.type == EtsTypes.NUMBER)
        val content = pager.pageContent.children.widgets.single() as Widget.Text<EtsExpression, SourceSpan>
        val contentNodes = mutableListOf<EtsNode>()
        walkEts(content.text.value, contentNodes::add)
        val page = pager.pageContent.index as EtsReference
        check(contentNodes.filterIsInstance<EtsReference>().any { it.symbol == page.symbol })
        check(contentNodes.filterIsInstance<EtsMember>().any { it == state.currentPage })
        val onChange = pager.onPageChange as EtsLambda
        check(onChange.type == EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID))
        val assignment = (onChange.body.single() as EtsExpressionStatement).expression as EtsAssignment
        check(assignment.target == state.currentPage)
        check((assignment.value as EtsReference).symbol == onChange.parameters.single().symbol)

        val body = HarmonyWidgetBackend().lower(model)
        val swiper = body.single() as EtsUiElement
        check((swiper.call.callee as EtsReference).symbol.name == "Swiper")
        check(swiper.call.arguments.single() == state.controller)
        check(swiper.attributes.map { (it.callee as EtsReference).symbol.name } ==
            listOf("index", "loop", "indicator", "onChange"))
        val pages = swiper.children!!.single() as EtsUiForEach
        check((pages.items as EtsArray).elements.map { (it as EtsLiteral).value } == listOf(0, 1, 2))
        check(pages.item.symbol == page.symbol && pages.body.single() is EtsUiElement)

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetpager.PagerProfile")
        File(output, "PagerProfile.ets").writeText(code)
        check("@Entry" in code && "@Component" in code && "export struct PagerProfile" in code)
        check("@State private pager_currentPage: number = 1;" in code)
        check("private pager_controller: SwiperController = new SwiperController();" in code)
        check("Swiper(this.pager_controller)" in code)
        check("ForEach([0, 1, 2] as Array<number>, (page: number) => {" in code)
        check(".index(this.pager_currentPage)" in code)
        check(".loop(false)" in code && ".indicator(false)" in code)
        check(".onChange((index: number): void => {" in code)
        check("this.pager_currentPage = index;" in code)
        check("Text(\"\" + \"Current \" + this.pager_currentPage + \": Page \" + page)" in code)
        check(listOf("onboarding", "animateScrollToPage", "changeIndex").none(code::contains))
        val fivePageCode = ComposeWidgetPipeline(
            EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
            .compile(module, "widgetpager.FivePageProfile")
        check("ForEach([0, 1, 2, 3, 4] as Array<number>, (page: number) => {" in fivePageCode)
        check("@State private pager_currentPage: number = 4;" in fivePageCode)

        val expected = linkedMapOf(
            "DynamicPageCount" to "positive integer literal",
            "EmptyPageCount" to "positive integer literal",
            "OutOfBoundsInitialPage" to "within pageCount",
            "UnsupportedPagerArgument" to "Unsupported androidx.compose.foundation.pager.HorizontalPager widget argument",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules())), StandardLibraryRuntime)
                    .compile(module, "widgetpager.$name")
                error("Accepted unsupported pager fixture $name")
            } catch (error: Unsupported) { error.diagnostic }
            check(message in failure.message) { "$name: ${failure.message}" }
            check(failure.source.file!!.endsWith("/PagerUnsupported.kt"))
            check(failure.source.start >= 0 && failure.source.end > failure.source.start)
            "$name\t${failure.code}\t${failure.source}\t${failure.message}"
        }
        File(output, "pager-diagnostics.tsv").writeText(diagnostics.joinToString("\n"))
    }
    println("PASS official HorizontalPager -> neutral Pager -> interactive typed Swiper")
}
