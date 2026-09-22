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

/** Test-only bytecode trace proving the production widget pipeline route. */
public final class PipelineSeamAgent {
    private static final Map<String, Set<String>> METHODS = Map.of(
        "dev/ets/pipeline/ComposeWidgetPipeline", Set.of("compile"),
        "dev/ets/compose/ComposeWidgetAdapter", Set.of("lower"),
        "dev/ets/harmony/HarmonyWidgetBackend", Set.of("lower"),
        "dev/ets/EtsProgram", Set.of("<init>"),
        "dev/ets/EtsValidator", Set.of("validate"),
        "dev/ets/ModulesKt", Set.of("emitEtsProgram"),
        "dev/ets/EtsPrinter", Set.of("program")
    );

    public static void premain(String options, Instrumentation instrumentation) {
        if (!System.getProperty("sun.java.command", "").startsWith(
                "dev.ets.widgettest.CoreProfilePipelineProbeKt ")) return;
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
                        if (!methods.contains(methodName)) return target;
                        return new MethodVisitor(Opcodes.ASM9, target) {
                            private void trace(String event) {
                                super.visitFieldInsn(Opcodes.GETSTATIC, "java/lang/System", "err", "Ljava/io/PrintStream;");
                                super.visitLdcInsn("WIDGET_SEAM " + name.substring("dev/ets/".length()) + "." + methodName + ":" + event);
                                super.visitMethodInsn(Opcodes.INVOKEVIRTUAL, "java/io/PrintStream", "println", "(Ljava/lang/String;)V", false);
                            }
                            @Override public void visitCode() { super.visitCode(); trace("enter"); }
                            @Override public void visitInsn(int opcode) {
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
