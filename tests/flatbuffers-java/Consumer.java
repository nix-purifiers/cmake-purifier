// SPDX-License-Identifier: MIT
import com.google.flatbuffers.FlatBufferBuilder;
import java.nio.ByteBuffer;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import proof.Envelope;
import proof.Value;
public final class Consumer {
  public static void main(String[] args) throws Exception {
    byte[] cpp = HexFormat.of().parseHex(args[0]);
    Envelope.ValidateVersion(); Value.ValidateVersion();
    if (Envelope.getRootAsEnvelope(ByteBuffer.wrap(cpp)).value().answer() != 42) throw new AssertionError();
    if (Value.class.getMethod("answer").getReturnType() != (args[3].equals("32") ? int.class : long.class)) throw new AssertionError();
    FlatBufferBuilder builder = new FlatBufferBuilder(0);
    int value = Value.createValue(builder, 42);
    int root = Envelope.createEnvelope(builder, value);
    Envelope.finishEnvelopeBuffer(builder, root);
    byte[] wire = builder.sizedByteArray();
    if (Envelope.getRootAsEnvelope(ByteBuffer.wrap(wire)).value().answer() != 42) throw new AssertionError();
    System.out.println("WIRE\t" + HexFormat.of().formatHex(wire));
    List<String> names = new ArrayList<>(Files.readAllLines(Path.of(args[4])));
    names.addAll(List.of("com/google/flatbuffers/Table.class", "com/google/flatbuffers/FlatBufferBuilder.class", "com/google/flatbuffers/Constants.class"));
    for (String entry : names) {
      Class<?> type = Class.forName(entry.substring(0, entry.length()-6).replace('/', '.'));
      Path origin = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath();
      Path expected = Path.of(entry.startsWith("com/google/flatbuffers/") ? args[2] : args[1]).toRealPath();
      if (!origin.equals(expected)) throw new AssertionError(origin + " != " + expected);
      try (var stream = type.getResourceAsStream("/"+entry)) {
        System.out.println("CLASS\t" + entry + "\t" + origin + "\t" + HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(stream.readAllBytes())));
      }
    }
  }
}
