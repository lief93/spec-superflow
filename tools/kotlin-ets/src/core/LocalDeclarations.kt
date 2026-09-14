@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.backend.common.LoweringContext
import org.jetbrains.kotlin.backend.common.ir.SharedVariablesManager
import org.jetbrains.kotlin.backend.common.lower.DeclarationIrBuilder
import org.jetbrains.kotlin.backend.common.lower.LocalDeclarationsLowering
import org.jetbrains.kotlin.backend.common.lower.SharedVariablesLowering
import org.jetbrains.kotlin.backend.jvm.JvmBackendContext
import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.ir.IrElement
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

/** Identity, not an origin-name/prefix match, authorizes the generated runtime class. */
val ETS_SHARED_VARIABLE_CELL = IrDeclarationOriginImpl("ETS_SHARED_VARIABLE_CELL", isSynthetic = true)

/** Capture discovery, lifting, recursion and type substitution belong to the official passes. */
internal fun lowerLocalDeclarations(input: JvmFir2IrPipelineArtifact) {
    val module = input.result.irModuleFragment
    val work = mutableListOf<Pair<IrBody, IrDeclaration>>()
    module.acceptChildrenVoid(object : IrElementVisitorVoid {
        private var owner: IrDeclaration? = null
        override fun visitElement(element: IrElement) {
            val previous = owner
            if (element is IrDeclaration) owner = element
            if (element is IrBody) {
                if (namedLocals(element).isNotEmpty()) work.add(element to checkNotNull(owner))
            } else element.acceptChildrenVoid(this)
            owner = previous
        }
    })
    if (work.isEmpty()) return
    val context = createJvmLoweringContext(input)
    val cells = SourceCellManager(context)
    val sharedContext = object : LoweringContext by context {
        override val sharedVariablesManager: SharedVariablesManager = cells
    }
    val shared = SharedVariablesLowering(sharedContext)
    val local = LocalDeclarationsLowering(context, remapTypesInExtractedLocalFunctions = true)
    for ((body, owner) in work) {
        val diagnostics = DiagnosticSink(owner.fileOrNull?.fileEntry?.name)
        body.acceptChildrenVoid(object : IrElementVisitorVoid {
            override fun visitElement(element: IrElement) {
                if (element is IrClass) diagnostics.unsupported(element, "Local classes are not supported by the ETS local declaration phase")
                element.acceptChildrenVoid(this)
            }
        })
        shared.lower(body, owner)
        local.lower(body, owner)
        namedLocals(body).firstOrNull()?.let {
            diagnostics.unsupported(it, "Official local declaration lowering left an unsupported nested function")
        }
    }
    module.patchDeclarationParents()
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
