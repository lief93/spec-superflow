import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.Map;
import java.util.Set;
import org.jetbrains.org.objectweb.asm.ClassReader;
import org.jetbrains.org.objectweb.asm.ClassVisitor;
import org.jetbrains.org.objectweb.asm.ClassWriter;
import org.jetbrains.org.objectweb.asm.MethodVisitor;
import org.jetbrains.org.objectweb.asm.Opcodes;

/** Test-only tracing of the real CLI; no production callbacks or alternate compiler entry. */
public final class CliSeamAgent {
    private static final Map<String, Set<String>> METHODS = Map.of(
        "dev/ets/EtsLoweringPhases", Set.of("run"),
        "dev/ets/pipeline/ComposeWidgetPipeline", Set.of("lower"),
        "dev/ets/IrToEts", Set.of("program"),
        "dev/ets/IrModuleToEts", Set.of("lower"),
        "dev/ets/IrFileToEts", Set.of("lower"),
        "dev/ets/EtsProgram", Set.of("<init>"),
        "dev/ets/EtsValidator", Set.of("validate"),
        "dev/ets/EtsPrinter", Set.of("program", "function", "clazz", "global"),
        "dev/ets/ModulesKt", Set.of("emitEtsProgram", "emitEtsModules")
    );

    public static void premain(String options, Instrumentation instrumentation) {
        // JAVA_TOOL_OPTIONS also reaches the launcher's compiler and jar commands.
        if (!System.getProperty("sun.java.command", "").startsWith("dev.ets.MainKt ")) return;
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(ClassLoader loader, String name, Class<?> redefined,
                    ProtectionDomain domain, byte[] bytes) {
                Set<String> methods = METHODS.get(name);
                if (methods == null) return null;
                ClassWriter writer = new ClassWriter(ClassWriter.COMPUTE_MAXS);
                new ClassReader(bytes).accept(new ClassVisitor(Opcodes.ASM9, writer) {
                    @Override
                    public MethodVisitor visitMethod(int access, String methodName, String descriptor,
                            String signature, String[] exceptions) {
                        MethodVisitor target = super.visitMethod(access, methodName, descriptor, signature, exceptions);
                        // Only the internal phase entry has a module-name suffix. Do not
                        // mistake validate$lambda helpers for whole-program validation.
                        String method = name.equals("dev/ets/EtsLoweringPhases") && methodName.startsWith("run$")
                            ? "run" : methodName;
                        if (!methods.contains(method)) return target;
                        return new MethodVisitor(Opcodes.ASM9, target) {
                            private void trace(String event) {
                                super.visitFieldInsn(Opcodes.GETSTATIC, "java/lang/System", "err", "Ljava/io/PrintStream;");
                                super.visitLdcInsn("ETS_SEAM " + name.substring("dev/ets/".length()) + "." + method + ":" + event);
                                super.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/io/PrintStream", "println", "(Ljava/lang/String;)V", false);
                            }
                            @Override
                            public void visitCode() {
                                super.visitCode();
                                trace("enter");
                            }
                            @Override
                            public void visitInsn(int opcode) {
                                if (opcode == Opcodes.ARETURN || opcode == Opcodes.RETURN) trace("exit");
                                super.visitInsn(opcode);
                            }
                        };
                    }
                }, 0);
                return writer.toByteArray();
            }
        });
    }
}
