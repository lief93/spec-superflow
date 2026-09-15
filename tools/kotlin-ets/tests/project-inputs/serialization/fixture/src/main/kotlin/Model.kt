package pluginfixture

import kotlinx.serialization.KSerializer
import kotlinx.serialization.Serializer

data class Model(val value: Int)

@OptIn(kotlinx.serialization.ExperimentalSerializationApi::class)
@Serializer(forClass = Model::class)
object ModelSerializer : KSerializer<Model>

fun descriptorName(): String = ModelSerializer.descriptor.serialName
