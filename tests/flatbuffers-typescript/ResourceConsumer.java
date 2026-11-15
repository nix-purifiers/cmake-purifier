// SPDX-License-Identifier: MIT
import java.net.URLClassLoader;
import java.net.JarURLConnection;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
public class ResourceConsumer {
  public static void main(String[] args) throws Exception {
    Path jar=Path.of(args[0]).toRealPath();int count=0;
    java.net.URL[] urls=args.length>3?new java.net.URL[]{jar.toUri().toURL(),Path.of(args[3]).toUri().toURL(),Path.of(args[4]).toUri().toURL()}:new java.net.URL[]{jar.toUri().toURL()};
    try(var loader=new URLClassLoader(urls,null)) {
      if(args.length>3){
        var owned=Class.forName("proof.Envelope",true,loader);var runtime=Class.forName("com.google.flatbuffers.Table",true,loader);
        if(!Path.of(owned.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath().equals(Path.of(args[3]).toRealPath()) || !Path.of(runtime.getProtectionDomain().getCodeSource().getLocation().toURI()).toRealPath().equals(Path.of(args[4]).toRealPath()))throw new AssertionError("class origin");
        var root=owned.getMethod("getRootAsEnvelope",java.nio.ByteBuffer.class).invoke(null,java.nio.ByteBuffer.wrap(HexFormat.of().parseHex(args[5])));var value=owned.getMethod("value").invoke(root);var answer=(Number)value.getClass().getMethod("answer").invoke(value);if(answer.longValue()!=42)throw new AssertionError(answer);
      }
      for(String row:Files.readAllLines(Path.of(args[1]))) {
        String[] fields=row.split("\\t");String name=args[2]+fields[0];var origin=loader.getResource(name);
        if(origin==null || !(origin.openConnection() instanceof JarURLConnection connection) || !Path.of(connection.getJarFileURL().toURI()).toRealPath().equals(jar))throw new AssertionError(name);
        try(var stream=loader.getResourceAsStream(name)) {if(!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(stream.readAllBytes())).equals(fields[1]))throw new AssertionError(name);}
        count++;
      }
    }
    System.out.println(count);
  }
}
