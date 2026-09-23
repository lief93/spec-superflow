package dev.ets.projectinputcontract

import dev.ets.AdapterModules
import dev.ets.examples.ExampleProjectInputsModule

fun main() {
    print(AdapterModules(listOf(ExampleProjectInputsModule())).manifestJson())
}
