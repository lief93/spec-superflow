package multimodule

class Model(val count: Int)

fun label(model: Model): String = "Count " + model.count
