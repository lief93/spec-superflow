@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.LoweringContext
import org.jetbrains.kotlin.backend.common.ir.SharedVariablesManager
import org.jetbrains.kotlin.backend.common.lower.DeclarationIrBuilder
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.backend.common.lower.LocalClassPopupLowering
import org.jetbrains.kotlin.backend.common.lower.ClosureAnnotator
import org.jetbrains.kotlin.backend.common.lower.SharedVariablesLowering
import org.jetbrains.kotlin.backend.common.lower.InnerClassesLowering
import org.jetbrains.kotlin.backend.common.lower.InnerClassesMemberBodyLowering
import org.jetbrains.kotlin.backend.common.lower.InnerClassConstructorCallsLowering
import org.jetbrains.kotlin.backend.jvm.JvmBackendContext
import org.jetbrains.kotlin.backend.jvm.JvmLoweredDeclarationOrigin
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.irAttribute
import org.jetbrains.kotlin.ir.builders.*
import org.jetbrains.kotlin.ir.builders.declarations.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.expressions.*
import org.jetbrains.kotlin.ir.expressions.impl.*
import org.jetbrains.kotlin.ir.symbols.IrValueSymbol
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name
import org.jetbrains.kotlin.utils.DFS

/** Identity, not an origin-name/prefix match, authorizes the generated runtime class. */
val ETS_SHARED_VARIABLE_CELL = IrDeclarationOriginImpl("ETS_SHARED_VARIABLE_CELL", isSynthetic = true)

private var IrClass.originalSourceExported: Boolean? by irAttribute(followAttributeOwner = true)

internal data class SourceInnerClassBinding(
    val outer: IrClass,
    val field: IrField,
    val constructor: IrConstructor,
    val parameter: IrValueParameter,
    val source: SourceSpan,
)

private var IrClass.originalInnerBinding: SourceInnerClassBinding? by irAttribute(followAttributeOwner = false)

internal fun sourceInnerClassBinding(declaration: IrClass): SourceInnerClassBinding? = declaration.originalInnerBinding

internal fun sourceClassIsExported(declaration: IrClass): Boolean = declaration.originalSourceExported
    ?: (declaration.visibility != DescriptorVisibilities.LOCAL && !DescriptorVisibilities.isPrivate(declaration.visibility))

/** Capture discovery, lifting, recursion and type substitution belong to the official passes. */
internal fun lowerLocalDeclarations(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val classes = sourceClasses(module)
    classes.forEach { declaration ->
        var current: IrDeclarationParent = declaration
        var exported = true
        while (current is IrDeclaration) {
            if (current is IrFunction || (current is IrDeclarationWithVisibility &&
                    (current.visibility == DescriptorVisibilities.LOCAL || DescriptorVisibilities.isPrivate(current.visibility)))) {
                exported = false
            }
            current = current.parent
        }
        declaration.originalSourceExported = exported
        if (declaration.isInner) validateInnerClass(declaration)
        if (declaration.parent !is IrFile && (declaration.isAnonymousObject || declaration.kind != ClassKind.CLASS)) {
            DiagnosticSink(declaration.fileOrNull?.fileEntry?.name).unsupported(declaration,
                "Nested/local declarations require a non-inner named source class")
        }
    }
    val work = mutableListOf<Pair<IrBody, IrDeclaration>>()
    module.acceptChildrenVoid(object : IrElementVisitorVoid {
        private var owner: IrDeclaration? = null
        override fun visitElement(element: IrElement) {
            val previous = owner
            if (element is IrDeclaration) owner = element
            if (element is IrBody) {
                if (namedLocals(element).isNotEmpty() || sourceClasses(element).isNotEmpty()) work.add(element to checkNotNull(owner))
            } else element.acceptChildrenVoid(this)
            owner = previous
        }
    })
    if (work.isEmpty() && classes.none { it.parent is IrClass }) return
    val context = createJvmLoweringContext(input)
    val cells = SourceCellManager(context)
    val sharedContext = object : LoweringContext by context {
        override val sharedVariablesManager: SharedVariablesManager = cells
    }
    val shared = SharedVariablesLowering(sharedContext)
    val local = LocalDeclarationsLowering(context, remapTypesInExtractedLocalFunctions = true)
    for ((body, owner) in work) {
        val diagnostics = DiagnosticSink(owner.fileOrNull?.fileEntry?.name)
        val localClasses = sourceClasses(body).filter { it.visibility == DescriptorVisibilities.LOCAL }
        if (localClasses.isNotEmpty()) {
            val closures = ClosureAnnotator(body, owner)
            localClasses.forEach { declaration ->
                val closure = closures.getClassClosure(declaration)
                if (closure.capturedTypeParameters.isNotEmpty()) {
                    diagnostics.unsupported(declaration, "Local class captured type parameters are not supported")
                }
                if (closure.capturedValues.isNotEmpty() && declaration.superTypes.any { !it.isAny() }) {
                    diagnostics.unsupported(declaration, "Captured local class inheritance is not supported")
                }
            }
        }
        shared.lower(body, owner)
        local.lower(body, owner)
        namedLocals(body).firstOrNull()?.let {
            diagnostics.unsupported(it, "Official local declaration lowering left an unsupported nested function")
        }
    }
    val popup = LocalClassPopupLowering(context)
    module.files.forEach(popup::lower)
    val inners = classes.filter { it.isInner }
    if (inners.isNotEmpty()) {
        val outerOwners = inners.associateWith { it.parent as IrClass }
        val constructors = inners.associateWith { it.constructors.single() }
        val declarations = InnerClassesLowering(context)
        val members = InnerClassesMemberBodyLowering(context)
        val calls = InnerClassConstructorCallsLowering(context)
        module.files.forEach(declarations::lower)
        module.files.forEach(members::lower)
        module.files.forEach(calls::lower)
        inners.forEach { inner ->
            val field = context.innerClassesSupport.getOuterThisField(inner)
            val constructor = context.innerClassesSupport.getInnerClassConstructorWithOuterThisParameter(constructors.getValue(inner))
            val parameter = constructor.valueParameters.first()
            check(field.origin === IrDeclarationOrigin.FIELD_FOR_OUTER_THIS &&
                parameter.origin === JvmLoweredDeclarationOrigin.FIELD_FOR_OUTER_THIS)
            inner.originalInnerBinding = SourceInnerClassBinding(outerOwners.getValue(inner), field, constructor, parameter,
                SourceSpan(inner.fileOrNull!!.fileEntry.name, inner.startOffset, inner.endOffset))
        }
    }
    // Mirror JS static class placement, retaining the original symbols, names and source file.
    fun extractNested(declaration: IrClass, file: IrFile) {
        declaration.declarations.filterIsInstance<IrClass>().forEach { nested ->
            extractNested(nested, file)
            declaration.declarations.remove(nested)
            nested.parent = file
            file.declarations.add(nested)
        }
    }
    module.files.forEach { file -> file.declarations.filterIsInstance<IrClass>().forEach { extractNested(it, file) } }
    // ES class evaluation needs local bases first; use the compiler's graph utility.
    module.files.forEach { file ->
        val declarations = file.declarations.toList()
        val owned = declarations.toSet()
        val ordered = DFS.topologicalOrder(declarations) { declaration ->
            (declaration as? IrClass)?.superTypes.orEmpty().mapNotNull { it.classOrNull?.owner }.filter { it in owned }
        }.asReversed()
        file.declarations.clear()
        file.declarations.addAll(ordered)
    }
    module.patchDeclarationParents()
}

private fun validateInnerClass(declaration: IrClass) {
    val diagnostics = DiagnosticSink(declaration.fileOrNull?.fileEntry?.name)
    val outer = declaration.parent as? IrClass
    if (outer == null || (outer.parent !is IrFile && !outer.isInner) || outer.kind != ClassKind.CLASS ||
        outer.isAnonymousObject || declaration.isAnonymousObject || declaration.kind != ClassKind.CLASS) {
        diagnostics.unsupported(declaration, "Inner classes require a named top-level outer source class")
    }
    if (outer.isInner) validateInnerClass(outer)
    if (outer.typeParameters.isNotEmpty() || declaration.typeParameters.isNotEmpty()) {
        diagnostics.unsupported(declaration, "Inner class generic binders are not supported")
    }
    val constructors = declaration.constructors.toList()
    if (constructors.size != 1 || !constructors.single().isPrimary) {
        diagnostics.unsupported(declaration, "Inner classes require one primary constructor")
    }
    if (declaration.superTypes.any { !it.isAny() }) {
        diagnostics.unsupported(declaration, "Inner classes require Any-only heritage")
    }
}

private fun sourceClasses(element: IrElement): List<IrClass> {
    val result = mutableListOf<IrClass>()
    element.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrClass) result.add(element)
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

private fun namedLocals(body: IrBody): List<IrSimpleFunction> {
    val result = mutableListOf<IrSimpleFunction>()
    body.acceptChildrenVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrSimpleFunction && element.visibility == DescriptorVisibilities.LOCAL && !element.name.isSpecial) {
                result.add(element)
            }
            element.acceptChildrenVoid(this)
        }
    })
    return result
}

/** A target runtime representation adapter, not a replacement capture-analysis algorithm. */
private class SourceCellManager(private val context: JvmBackendContext) : SharedVariablesManager {
    private val generator = IrGeneratorContextBase(context.irBuiltIns)
    private val cells = linkedMapOf<IrFile, IrClass>()
    private val properties = mutableMapOf<IrClass, IrProperty>()
    private val builtIns get() = context.irBuiltIns

    override fun declareSharedVariable(originalDeclaration: IrVariable): IrVariable {
        val file = originalDeclaration.fileOrNull ?: error("Captured source variable has no file")
        val initializer = originalDeclaration.initializer ?: DiagnosticSink(file.fileEntry.name).unsupported(
            originalDeclaration, "Captured variable without an initializer is not supported by the ETS shared cell")
        val cell = cells.getOrPut(file) { createCell(file, originalDeclaration) }
        val cellType = cell.symbol.typeWith(originalDeclaration.type)
        val creation = IrConstructorCallImpl.fromSymbolOwner(initializer.startOffset, initializer.endOffset,
            cellType, cell.constructors.single().symbol).apply {
            putTypeArgument(0, originalDeclaration.type)
            putValueArgument(0, initializer)
        }
        return buildVariable(originalDeclaration.parent, originalDeclaration.startOffset, originalDeclaration.endOffset,
            originalDeclaration.origin, originalDeclaration.name, cellType).apply { this.initializer = creation }
    }

    override fun defineSharedValue(originalDeclaration: IrVariable, sharedVariableDeclaration: IrVariable) = sharedVariableDeclaration

    override fun getSharedValue(sharedVariableSymbol: IrValueSymbol, originalGet: IrGetValue): IrExpression {
        val property = properties.getValue(sharedVariableSymbol.owner.type.classOrNull!!.owner)
        return IrCallImpl.fromSymbolOwner(originalGet.startOffset, originalGet.endOffset, originalGet.type,
            property.getter!!.symbol).apply {
            origin = originalGet.origin
            dispatchReceiver = IrGetValueImpl(originalGet.startOffset, originalGet.endOffset,
                sharedVariableSymbol.owner.type, sharedVariableSymbol)
        }
    }

    override fun setSharedValue(sharedVariableSymbol: IrValueSymbol, originalSet: IrSetValue): IrExpression {
        val property = properties.getValue(sharedVariableSymbol.owner.type.classOrNull!!.owner)
        return IrCallImpl.fromSymbolOwner(originalSet.startOffset, originalSet.endOffset, builtIns.unitType,
            property.setter!!.symbol).apply {
            origin = originalSet.origin
            dispatchReceiver = IrGetValueImpl(originalSet.startOffset, originalSet.endOffset,
                sharedVariableSymbol.owner.type, sharedVariableSymbol)
            putValueArgument(0, originalSet.value)
        }
    }

    private fun createCell(file: IrFile, source: IrVariable): IrClass {
        val start = source.startOffset
        val end = source.endOffset
        val cell = context.irFactory.buildClass {
            startOffset = start
            endOffset = end
            origin = ETS_SHARED_VARIABLE_CELL
            name = Name.identifier("__etsSharedCell${cells.size}")
        }.apply {
            parent = file
            superTypes = listOf(builtIns.anyType)
        }
        val parameter = cell.addTypeParameter {
            startOffset = start
            endOffset = end
            name = Name.identifier("T")
            superTypes.add(builtIns.anyNType)
        }
        cell.createThisReceiverParameter()
        val valueType = parameter.defaultType
        val property = cell.addProperty {
            startOffset = start
            endOffset = end
            name = Name.identifier("value")
            isVar = true
        }
        val field = property.addBackingField {
            startOffset = start
            endOffset = end
            type = valueType
        }
        val getter = property.addGetter {
            startOffset = start
            endOffset = end
            origin = IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR
            returnType = valueType
        }
        getter.dispatchReceiverParameter = cell.thisReceiver!!.copyTo(getter, type = cell.defaultType)
        getter.body = DeclarationIrBuilder(generator, getter.symbol, start, end).irBlockBody {
            +irReturn(irGetField(irGet(getter.dispatchReceiverParameter!!), field))
        }
        val setter = property.addSetter {
            startOffset = start
            endOffset = end
            origin = IrDeclarationOrigin.DEFAULT_PROPERTY_ACCESSOR
            returnType = builtIns.unitType
        }
        setter.dispatchReceiverParameter = cell.thisReceiver!!.copyTo(setter, type = cell.defaultType)
        val newValue = setter.addValueParameter {
            startOffset = start
            endOffset = end
            name = Name.identifier("newValue")
            type = valueType
        }
        setter.body = DeclarationIrBuilder(generator, setter.symbol, start, end).irBlockBody {
            +irSetField(irGet(setter.dispatchReceiverParameter!!), field, irGet(newValue))
        }
        val constructor = cell.addConstructor {
            startOffset = start
            endOffset = end
            isPrimary = true
            returnType = cell.defaultType
        }
        val initial = constructor.addValueParameter {
            startOffset = start
            endOffset = end
            name = Name.identifier("initial")
            type = valueType
        }
        constructor.body = DeclarationIrBuilder(generator, constructor.symbol, start, end).irBlockBody {
            +irDelegatingConstructorCall(builtIns.anyClass.owner.constructors.single())
            +irSetField(irGet(cell.thisReceiver!!), field, irGet(initial))
        }
        properties[cell] = property
        file.declarations.add(cell)
        return cell
    }
}
