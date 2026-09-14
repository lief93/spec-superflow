@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets

import org.jetbrains.kotlin.cli.pipeline.jvm.JvmFir2IrPipelineArtifact
import org.jetbrains.kotlin.ir.IrElement
import org.jetbrains.kotlin.ir.declarations.IrTypeParameter
import org.jetbrains.kotlin.ir.types.IrTypeSystemContextImpl
import org.jetbrains.kotlin.ir.util.isSubtypeOf
import org.jetbrains.kotlin.ir.visitors.*

/** ETS has one bound; collapse only a conjunction proven equivalent by Kotlin. */
internal fun lowerRedundantGenericBounds(input: JvmFir2IrPipelineArtifact) {
    val types = IrTypeSystemContextImpl(input.result.irBuiltIns)
    input.result.irModuleFragment.acceptVoid(object : IrElementVisitorVoid {
        override fun visitElement(element: IrElement) = element.acceptChildrenVoid(this)
        override fun visitTypeParameter(declaration: IrTypeParameter) {
            val bounds = declaration.superTypes
            if (bounds.size > 1) {
                bounds.firstOrNull { candidate -> bounds.all { candidate.isSubtypeOf(it, types) } }?.let {
                    declaration.superTypes = listOf(it)
                }
            }
            super.visitTypeParameter(declaration)
        }
    })
}
