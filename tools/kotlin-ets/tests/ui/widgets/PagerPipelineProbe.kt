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
        val backend = EtsBackend(sink, listOf(StandardLibraryRules(), ComposeDimensionRule()))
        val plan = ComposeStateLowering(backend.language, sink).lower(entry, Scope(), "PagerProfile")
        check(plan.fields.map { it.symbol.name to it.symbol.type } == listOf(
            "pager_currentPage" to EtsTypes.NUMBER,
            "pager_controller" to EtsNamedType("SwiperController"),
            "__etsState_selected" to EtsTypes.NUMBER))
        check(plan.fields[0].state && plan.fields[0].visibility == EtsVisibility.PRIVATE)
        check(!plan.fields[1].state && plan.fields[1].visibility == EtsVisibility.PRIVATE)
        check(plan.fields[2].state && plan.fields[2].visibility == EtsVisibility.PRIVATE)
        check((plan.fields[0].initializer as EtsLiteral).value == 1)
        check(plan.fields[1].initializer is EtsNew)
        check((plan.fields[2].initializer as EtsLiteral).value == -1)
        val state = plan.pagers.values.single()
        check((state.pageCount as EtsLiteral).value == 4)

        val model = ComposeWidgetAdapter(backend.language, sink, plan.pagers)
            .lower(entry, plan.scope, plan.handledStatements)
        val root = model.widgets.single() as Widget.Column<EtsExpression, SourceSpan>
        check(root.children.widgets.size == 4)
        val pager = root.children.widgets[0] as Widget.Pager<EtsExpression, SourceSpan>
        check(pager.currentPage == state.currentPage && pager.controller == state.controller)
        check((pager.pageCount as EtsLiteral).value == 4)
        check((pager.enabled as EtsLiteral).value == true)
        check(pager.pageContent.index.type == EtsTypes.NUMBER)
        val page = pager.pageContent.index as EtsReference
        val pageContent = pager.pageContent.children.widgets.single() as Widget.Conditional<EtsExpression, SourceSpan>
        check(pageContent.branches.size == 2 && pageContent.branches.last().condition == null)
        val pageConditionNodes = mutableListOf<EtsNode>()
        walkEts(checkNotNull(pageContent.branches.first().condition), pageConditionNodes::add)
        check(pageConditionNodes.filterIsInstance<EtsReference>().any { it.symbol == page.symbol })
        check(pageContent.branches.map { branch ->
            ((branch.children.widgets.single() as Widget.Text).text.value as EtsLiteral).value
        } == listOf("A", "B"))
        val indicator = root.children.widgets[1] as Widget.Text<EtsExpression, SourceSpan>
        val indicatorNodes = mutableListOf<EtsNode>()
        walkEts(indicator.text.value, indicatorNodes::add)
        check(indicatorNodes.filterIsInstance<EtsMember>().any { it == state.currentPage })
        val buttons = root.children.widgets[2] as Widget.Conditional<EtsExpression, SourceSpan>
        check(buttons.branches.size == 2 && buttons.branches.last().condition == null)
        check(buttons.branches.map { branch ->
            val button = branch.children.widgets.single() as Widget.Button
            ((button.content.widgets.single() as Widget.Text).text.value as EtsLiteral).value
        } == listOf("Finish", "Next"))
        val onChange = pager.onPageChange as EtsLambda
        check(onChange.type == EtsFunctionType(listOf(EtsTypes.NUMBER), EtsTypes.VOID))
        val assignment = (onChange.body.single() as EtsExpressionStatement).expression as EtsAssignment
        check(assignment.target == state.currentPage)
        check((assignment.value as EtsReference).symbol == onChange.parameters.single().symbol)

        val body = HarmonyWidgetBackend().lower(model)
        val targetNodes = mutableListOf<EtsNode>()
        body.forEach { walkEts(it, targetNodes::add) }
        val swiper = targetNodes.filterIsInstance<EtsUiElement>().single {
            (it.call.callee as? EtsReference)?.symbol?.name == "Swiper"
        }
        check((swiper.call.callee as EtsReference).symbol.name == "Swiper")
        check(swiper.call.arguments.single() == state.controller)
        check(swiper.attributes.map { (it.callee as EtsReference).symbol.name } ==
            listOf("width", "index", "loop", "indicator", "disableSwipe", "onChange"))
        check((swiper.attributes[4].arguments.single() as EtsUnary).operand == pager.enabled)
        val pages = swiper.children!!.single() as EtsUiForEach
        check((pages.items as EtsArray).elements.map { (it as EtsLiteral).value } == listOf(0, 1, 2, 3))
        check(pages.item.symbol == page.symbol && pages.body.single() is EtsIf)

        val code = ComposeWidgetPipeline(backend, StandardLibraryRuntime)
            .compile(module, "widgetpager.PagerProfile")
        File(output, "PagerProfile.ets").writeText(code)
        check("@Entry" in code && "@Component" in code && "export struct PagerProfile" in code)
        check("@State private pager_currentPage: number = 1;" in code)
        check("private pager_controller: SwiperController = new SwiperController();" in code)
        check("@State private __etsState_selected: number = -1;" in code)
        check("Swiper(this.pager_controller)" in code)
        check("ForEach([0, 1, 2, 3] as Array<number>, (page: number) => {" in code)
        check("if (page < 3)" in code && "Text(\"A\")" in code && "Text(\"B\")" in code)
        check(".index(this.pager_currentPage)" in code)
        check(".width(\"100%\")" in code)
        check(".loop(false)" in code && ".indicator(false)" in code)
        check(".disableSwipe(! true)" in code)
        check(".onChange((index: number): void => {" in code)
        check("this.pager_currentPage = index;" in code)
        check("Text(\"\" + \"Indicator \" + (this.pager_currentPage + 1 | 0) + \"/4\")" in code)
        check("if (this.pager_currentPage === 3)" in code)
        check("Text(\"Finish\")" in code && "Text(\"Next\")" in code)
        check("this.__etsState_selected = this.pager_currentPage;" in code)
        check("Text(\"\" + \"Selected \" + this.__etsState_selected)" in code)
        check(listOf("onboarding", "animateScrollToPage", "changeIndex").none(code::contains))
        val fivePageCode = ComposeWidgetPipeline(
            EtsBackend(DiagnosticSink(), listOf(StandardLibraryRules(), ComposeDimensionRule())), StandardLibraryRuntime)
            .compile(module, "widgetpager.FivePageProfile")
        check("ForEach([0, 1, 2, 3, 4] as Array<number>, (page: number) => {" in fivePageCode)
        check("@State private pager_currentPage: number = 4;" in fivePageCode)
        check(".disableSwipe(! false)" in fivePageCode)

        val expected = linkedMapOf(
            "DynamicPageCount" to "positive integer literal",
            "EmptyPageCount" to "positive integer literal",
            "OutOfBoundsInitialPage" to "within pageCount",
            "InlinePagerState" to "requires source remembered PagerState",
            "ReversePager" to "Unsupported androidx.compose.foundation.pager.HorizontalPager widget argument: reverseLayout",
        )
        val diagnostics = expected.map { (name, message) ->
            val failure = try {
                ComposeWidgetPipeline(EtsBackend(DiagnosticSink(),
                    listOf(StandardLibraryRules(), ComposeDimensionRule())), StandardLibraryRuntime)
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
