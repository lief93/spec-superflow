@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.expressions.IrCall
import org.jetbrains.kotlin.ir.expressions.IrConst
import org.jetbrains.kotlin.ir.expressions.IrGetField
import org.jetbrains.kotlin.ir.types.IrType
import org.jetbrains.kotlin.ir.types.classOrNull
import org.jetbrains.kotlin.ir.visitors.IrElementVisitorVoid
import org.jetbrains.kotlin.ir.visitors.acceptChildrenVoid
import org.jetbrains.kotlin.ir.visitors.acceptVoid

private val focusSource = SourceSpan("EtsFocusManager.kt", -1, -1)
internal val focusManagerType = etsClassSymbol("EtsFocusManager", focusSource).type as EtsNamedType
internal val focusUIContextType = EtsNamedType("__etsUIContext", external = true)
private val focusManagerSingleton = EtsSymbol("compose:focusManager", "__etsFocusManager", focusManagerType, focusSource)
private val localFocusManagerMarker = EtsSymbol("compose:localFocusManager", "__etsLocalFocusManager",
    compositionLocalType, focusSource, external = true)
private val clearFocusSymbol = EtsSymbol("compose:clearFocus", "__etsClearFocus",
    EtsFunctionType(emptyList(), EtsTypes.VOID), focusSource, external = true)
private val activeUIContextSymbol = EtsSymbol("compose:activeUIContext", "__etsActiveUIContext",
    EtsNullableType(focusUIContextType), focusSource, external = true)
private val hostThisSymbol = EtsSymbol("arkui:host-this", "this",
    EtsNamedType("CustomComponent", external = true), focusSource, external = true)

/** True when any call reads the platform FocusManager composition local. */
internal fun requiresFocusManager(element: IrElement): Boolean {
    var required = false
    element.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) { element.acceptChildrenVoid(this) }
        override fun visitCall(expression: IrCall) {
            val owner = expression.symbol.owner
            if (sourceFile(owner) == null &&
                (symbolName(owner) == "androidx.compose.ui.focus.FocusManager.clearFocus" ||
                    owner.correspondingPropertySymbol?.owner?.let(::symbolName) ==
                        "androidx.compose.ui.platform.LocalFocusManager")) required = true
            expression.acceptChildrenVoid(this)
        }
    })
    return required
}

/** Capture `this.getUIContext()` in `aboutToAppear` so later composition callbacks can clear focus.
 *  Ordinary statements are valid here because this is a component method, not the UI DSL build body. */
internal fun focusContextInit(owner: IrElement, language: Language): EtsFunction {
    val at = language.source(owner)
    val getUIContext = EtsCall(
        EtsMember(EtsReference(hostThisSymbol, at), "getUIContext", EtsFunctionType(emptyList(), focusUIContextType), at),
        emptyList(), focusUIContextType, at)
    val capture = EtsExpressionStatement(EtsAssignment(EtsReference(activeUIContextSymbol, at), getUIContext, at), at)
    return EtsFunction("aboutToAppear", emptyList(), EtsTypes.VOID, listOf(capture), at, kind = EtsFunctionKind.METHOD)
}

/** LocalFocusManager.current is an opaque composition value. The only supported method, clearFocus,
 *  is a native focus-controller clear through the UIContext captured on the entry component. */
internal class ComposeFocusManagerRule : CallRule {
    override fun mapType(type: IrType, language: Language): EtsType? = type.classOrNull?.owner?.let {
        when (symbolName(it)) {
            "androidx.compose.ui.focus.FocusManager" -> if (sourceFile(it) == null) focusManagerType else null
            "androidx.compose.runtime.CompositionLocal",
            "androidx.compose.runtime.ProvidableCompositionLocal" -> compositionLocalType
            else -> null
        }
    }

    override fun lowerField(value: IrGetField, language: Language, scope: Scope): EtsExpression? {
        val name = value.symbol.owner.correspondingPropertySymbol?.owner?.let(::symbolName)
            ?: symbolName(value.symbol.owner)
        return if (name == "androidx.compose.ui.platform.LocalFocusManager")
            EtsReference(localFocusManagerMarker, language.source(value)) else null
    }

    override fun lower(call: IrCall, language: Language, scope: Scope): EtsExpression? {
        val owner = call.symbol.owner
        val at = language.source(call)
        if (isCompositionLocalCurrent(owner)) {
            if (compositionLocalName(call.dispatchReceiver, scope) !=
                "androidx.compose.ui.platform.LocalFocusManager") return null
            return EtsReference(focusManagerSingleton, at)
        }
        if (compositionLocalName(call, scope) == "androidx.compose.ui.platform.LocalFocusManager")
            return EtsReference(localFocusManagerMarker, at)
        if (sourceFile(owner) != null) return null
        if (symbolName(owner) == "androidx.compose.ui.focus.FocusManager.clearFocus") {
            val force = argument(call, "force")
            if (force != null && (force as? IrConst)?.value != true) {
                throw Unsupported(Diagnostic("UNSUPPORTED",
                    "FocusManager.clearFocus only supports the default force=true argument", at))
            }
            return EtsCall(EtsReference(clearFocusSymbol, at), emptyList(), EtsTypes.VOID, at)
        }
        return null
    }

    override fun targetImports(program: EtsProgram): List<EtsImport> = if (!usesRuntime(program)) emptyList() else
        listOf(EtsImport("@kit.ArkUI", "UIContext", "__etsUIContext"))

    override fun targetFiles(program: EtsProgram): List<EtsFile> =
        if (!usesType(program) && !usesRuntime(program)) emptyList() else listOf(EtsFile(focusSource.file!!, listOf(
            EtsClass(focusManagerType.name, listOf(EtsFunction("constructor", emptyList(), EtsTypes.VOID,
                emptyList(), focusSource, kind = EtsFunctionKind.CONSTRUCTOR)), focusSource, exported = true),
            EtsGlobal(focusManagerSingleton, EtsNew(focusManagerType, emptyList(), focusSource), false, exported = true))))

    private fun usesType(program: EtsProgram): Boolean {
        fun uses(type: EtsType): Boolean = when (type) {
            is EtsNamedType -> type.symbolId == focusManagerType.symbolId || type.arguments.any(::uses)
            is EtsFunctionType -> type.parameters.any(::uses) || uses(type.result)
            is EtsNullableType -> uses(type.inner)
            else -> false
        }
        var found = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) { node ->
            if (node is EtsExpression && uses(node.type) || node is EtsFunction && uses(node.symbol.type)) found = true
            if (node is EtsReference && node.symbol.id == focusManagerSingleton.id) found = true
        } } }
        return found
    }

    private fun usesRuntime(program: EtsProgram): Boolean {
        var found = false
        program.files.forEach { file -> file.declarations.forEach { declaration -> walkEts(declaration) {
            if (it is EtsReference && it.symbol.id in setOf(clearFocusSymbol.id, activeUIContextSymbol.id)) found = true
        } } }
        return found
    }
}

/** Runtime support for the focus manager: the active UI context is captured by the entry
 *  component and clearFocus delegates to the native focus controller. */
internal val focusSupport = """
let __etsActiveUIContext: __etsUIContext | null = null;

function __etsClearFocus(): void {
  __etsActiveUIContext?.getFocusController()?.clearFocus();
}
""".trimIndent().lines()
