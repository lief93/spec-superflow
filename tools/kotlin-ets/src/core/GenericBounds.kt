@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.descriptors.ClassKind
import org.jetbrains.kotlin.descriptors.DescriptorVisibilities
import org.jetbrains.kotlin.descriptors.Modality
import org.jetbrains.kotlin.ir.backend.js.utils.NameTable
import org.jetbrains.kotlin.ir.builders.declarations.buildClass
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.overrides.FakeOverrideBuilderStrategy
import org.jetbrains.kotlin.ir.overrides.IrFakeOverrideBuilder
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.util.*
import org.jetbrains.kotlin.ir.util.isSubtypeOf
import org.jetbrains.kotlin.ir.util.isNullable
import org.jetbrains.kotlin.ir.visitors.*
import org.jetbrains.kotlin.name.Name

val ETS_BOUND_CONSTRAINT = IrDeclarationOriginImpl("ETS_BOUND_CONSTRAINT")

/** Preserve Kotlin's conjunction using one equivalent bound or a named interface. */
internal fun lowerGenericBounds(input: JvmFir2IrPipelineArtifact) {
    val types = IrTypeSystemContextImpl(input.result.irBuiltIns)
    val parameters = mutableListOf<IrTypeParameter>()
    val reserved = mutableSetOf<String>()
    input.result.irModuleFragment.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) {
            if (element is IrDeclarationWithName) reserved += element.name.asString()
            element.acceptChildrenVoid(this)
        }
        override fun visitTypeParameter(declaration: IrTypeParameter) {
            parameters += declaration
            val bounds = declaration.superTypes
            if (bounds.size > 1) {
                bounds.firstOrNull { candidate -> bounds.all { candidate.isSubtypeOf(it, types) } }?.let {
                    declaration.superTypes = listOf(it)
                }
            }
            super.visitTypeParameter(declaration)
        }
    })
    val names = NameTable<IrTypeParameter>(reserved = reserved)
    data class Constraint(val source: IrTypeParameter, val bounds: List<IrType>, val helper: IrClass, val free: List<IrTypeParameter>)
    val constraints = parameters.filter { parameter -> parameter.superTypes.size > 1 && parameter.superTypes.all {
        !it.isNullable() && it.classOrNull?.owner?.let { owner -> owner.kind in setOf(ClassKind.CLASS, ClassKind.INTERFACE) && sourceFile(owner) != null } == true
    } }.sortedWith(compareBy({ it.file.fileEntry.name }, { it.startOffset }, { it.index })).map { parameter ->
        val free = linkedSetOf<IrTypeParameter>()
        fun collect(type: IrType) {
            if (type !is IrSimpleType) return
            (type.classifier.owner as? IrTypeParameter)?.let { if (free.add(it)) it.superTypes.forEach(::collect) }
            type.arguments.filterIsInstance<IrTypeProjection>().forEach { collect(it.type) }
        }
        parameter.superTypes.forEach(::collect)
        val owner = parameter.parent as IrDeclarationWithName
        val hint = "__etsBound_${owner.name}_${parameter.name}".replace(Regex("[^A-Za-z0-9_$]"), "_")
        val helper = parameter.factory.buildClass {
            startOffset = parameter.startOffset
            endOffset = parameter.endOffset
            origin = ETS_BOUND_CONSTRAINT
            name = Name.identifier(names.declareFreshName(parameter, hint))
            kind = if (parameter.superTypes.any { it.classOrNull?.owner?.kind == ClassKind.CLASS }) ClassKind.CLASS else ClassKind.INTERFACE
            modality = Modality.ABSTRACT
            visibility = DescriptorVisibilities.PUBLIC
        }.apply { parent = parameter.file }
        helper.copyTypeParameters(free.toList())
        Constraint(parameter, parameter.superTypes, helper, free.toList())
    }
    // Publish every bound before rebinding helpers, including recursive/dependent binders.
    constraints.forEach { it.source.superTypes = listOf(it.helper.typeWith(it.free.map { p -> p.defaultType })) }
    constraints.forEach { (parameter, bounds, helper, free) ->
        val substitution = IrTypeSubstitutor(free.map { it.symbol }, helper.typeParameters.map { it.defaultType }, allowEmptySubstitution = true)
        helper.superTypes = bounds.map(substitution::substitute)
        free.zip(helper.typeParameters).forEach { (original, copied) -> copied.superTypes = original.superTypes.map(substitution::substitute) }
        helper.createThisReceiverParameter()
        parameter.file.declarations += helper
    }
    val overrides = IrFakeOverrideBuilder(types, object : FakeOverrideBuilderStrategy.BindToPrivateSymbols(emptyMap()) {}, emptyList())
    constraints.filter { it.helper.kind == ClassKind.CLASS }.forEach {
        overrides.buildFakeOverridesForClass(it.helper, oldSignatures = false)
    }
}
