package dev.ets

import org.jetbrains.kotlin.ir.util.dump

fun main(args: Array<String>) {
    withKotlinFrontend(listOf("-no-stdlib", "-no-reflect", "-classpath", args[0]) + args.drop(1)) {
        println(it.module.dump())
    }
}
