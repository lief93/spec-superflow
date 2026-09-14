package binarytest

import java.io.File
import java.util.jar.JarEntry
import java.util.jar.JarInputStream
import java.util.jar.JarOutputStream
import org.jetbrains.org.objectweb.asm.*

/** A negative dependency fixture: preserve code/IR metadata but remove SourceFile. */
fun main(args: Array<String>) {
    JarInputStream(File(args[0]).inputStream()).use { input ->
        JarOutputStream(File(args[1]).outputStream(), input.manifest).use { output ->
            while (true) {
                val entry = input.nextJarEntry ?: break
                val bytes = input.readBytes()
                output.putNextEntry(JarEntry(entry.name))
                if (entry.name.endsWith(".class")) {
                    val writer = ClassWriter(0)
                    ClassReader(bytes).accept(object : ClassVisitor(Opcodes.ASM9, writer) {
                        override fun visitSource(source: String?, debug: String?) {}
                    }, 0)
                    output.write(writer.toByteArray())
                } else output.write(bytes)
                output.closeEntry()
            }
        }
    }
}
