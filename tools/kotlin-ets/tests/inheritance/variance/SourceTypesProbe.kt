@file:OptIn(org.jetbrains.kotlin.ir.symbols.UnsafeDuringIrConstructionAPI::class)
package dev.ets.variance.types

import dev.ets.*
import org.jetbrains.kotlin.ir.declarations.*
import org.jetbrains.kotlin.ir.types.*
import org.jetbrains.kotlin.ir.types.impl.IrCapturedType
import org.jetbrains.kotlin.ir.util.*

fun main(args: Array<String>) {
    lateinit var borrowed: SourceTypes
    lateinit var heldType: IrSimpleType
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) { frontend ->
        val declarations = frontend.module.files.flatMap { it.declarations }
        fun parameter(name: String) = declarations.filterIsInstance<IrSimpleFunction>().single {
            it.name.asString() == name
        }.valueParameters.first().type as IrSimpleType
        val out = parameter("readProjected")
        val into = parameter("writeProjected")
        val star = parameter("emptyProjected")
        val invariant = parameter("project")
        val value = declarations.filterIsInstance<IrClass>().single { it.name.asString() == "Value" }.defaultType
        val specific = declarations.filterIsInstance<IrClass>().single { it.name.asString() == "Specific" }.defaultType
        val types = frontend.types
        fun captured(type: IrSimpleType) = (types.capture(type).arguments.single() as IrTypeProjection).type as IrCapturedType
        check(captured(out).lowerType == null)
        check(captured(out).constructor.superTypes!!.any { it == value })
        check(captured(into).lowerType == specific)
        check(captured(star).lowerType == null)
        check(captured(star).constructor.superTypes!!.single().isNullableAny())
        check(types.capture(invariant) === invariant)
        check(types.isSubtypeOf(invariant, out) && types.isSubtypeOf(invariant, star))
        check(types.isSubtypeOf(specific, value) && !types.isSubtypeOf(value, specific))
        check(!types.isSubtypeOf(out, invariant))
        borrowed = types
        heldType = invariant
    }
    check(runCatching { borrowed.capture(heldType) }.exceptionOrNull() is IllegalStateException)
    check(runCatching { borrowed.isSubtypeOf(heldType, heldType) }.exceptionOrNull() is IllegalStateException)
    println("PASS official in/out/star capture, invariant identity, directional subtyping and two closed-session refusals")
}
