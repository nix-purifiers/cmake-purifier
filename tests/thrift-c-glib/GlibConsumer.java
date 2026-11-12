// SPDX-License-Identifier: MIT
import java.lang.foreign.*;
import java.lang.invoke.MethodHandle;
import java.nio.file.*;
import java.util.HexFormat;
import static java.lang.foreign.ValueLayout.*;
public class GlibConsumer {
  static final Linker LINK=Linker.nativeLinker();
  static SymbolLookup symbols;
  static MethodHandle fn(String name,FunctionDescriptor shape,boolean variadic){return variadic?LINK.downcallHandle(symbols.find(name).orElseThrow(),shape,Linker.Option.firstVariadicArg(2)):LINK.downcallHandle(symbols.find(name).orElseThrow(),shape);}
  static long type(String name)throws Throwable{return (long)fn(name,FunctionDescriptor.of(JAVA_LONG),false).invokeExact();}
  public static void main(String[] args)throws Throwable{
    try(Arena arena=Arena.ofConfined()){
      symbols=SymbolLookup.libraryLookup(Path.of(args[0]),arena);
      var nil=MemorySegment.NULL;
      var newInt=fn("g_object_new",FunctionDescriptor.of(ADDRESS,JAVA_LONG,ADDRESS,JAVA_INT,ADDRESS),true);
      var newPtr=fn("g_object_new",FunctionDescriptor.of(ADDRESS,JAVA_LONG,ADDRESS,ADDRESS,ADDRESS),true);
      var get=fn("g_object_get",FunctionDescriptor.ofVoid(ADDRESS,ADDRESS,ADDRESS,ADDRESS),true);
      var unref=fn("g_object_unref",FunctionDescriptor.ofVoid(ADDRESS),false);
      var write=fn("thrift_struct_write",FunctionDescriptor.of(JAVA_INT,ADDRESS,ADDRESS,ADDRESS),false);
      var read=fn("thrift_struct_read",FunctionDescriptor.of(JAVA_INT,ADDRESS,ADDRESS,ADDRESS),false);
      var transportRead=fn("thrift_transport_read",FunctionDescriptor.of(JAVA_INT,ADDRESS,ADDRESS,JAVA_INT,ADDRESS),false);
      var transportWrite=fn("thrift_transport_write",FunctionDescriptor.of(JAVA_INT,ADDRESS,ADDRESS,JAVA_INT,ADDRESS),false);
      var value=(MemorySegment)newInt.invokeExact(type("value_get_type"),arena.allocateFrom("answer"),42,nil);
      var envelope=(MemorySegment)newPtr.invokeExact(type("envelope_get_type"),arena.allocateFrom("value"),value,nil);
      var transport=(MemorySegment)newPtr.invokeExact(type("thrift_memory_buffer_get_type"),nil,nil,nil);
      var protocol=(MemorySegment)newPtr.invokeExact(type("thrift_binary_protocol_get_type"),arena.allocateFrom("transport"),transport,nil);
      byte[] expected=HexFormat.of().parseHex(args[1]);var error=arena.allocate(ADDRESS);
      int count=(int)write.invokeExact(envelope,protocol,error);if(count!=expected.length||!error.get(ADDRESS,0).equals(nil))throw new AssertionError("write");
      var bytes=arena.allocate(expected.length);count=(int)transportRead.invokeExact(transport,bytes,expected.length,error);if(count!=expected.length||!java.util.Arrays.equals(bytes.toArray(JAVA_BYTE),expected))throw new AssertionError("wire");
      int written=(int)transportWrite.invokeExact(transport,bytes,expected.length,error);if(written==0)throw new AssertionError("transport write");
      var restored=(MemorySegment)newPtr.invokeExact(type("envelope_get_type"),nil,nil,nil);count=(int)read.invokeExact(restored,protocol,error);if(count!=expected.length)throw new AssertionError("read");
      var childOut=arena.allocate(ADDRESS);get.invokeExact(restored,arena.allocateFrom("value"),childOut,nil);var child=childOut.get(ADDRESS,0);var answerOut=arena.allocate(JAVA_INT);get.invokeExact(child,arena.allocateFrom("answer"),answerOut,nil);int answer=answerOut.get(JAVA_INT,0);if(answer!=42)throw new AssertionError(answer);
      for(String typeName:new String[]{"qa_value_get_type","qb_value_get_type"}){
        var object=(MemorySegment)newPtr.invokeExact(type(typeName),nil,nil,nil);var actual=arena.allocate(JAVA_INT);get.invokeExact(object,arena.allocateFrom("answer"),actual,nil);if(actual.get(JAVA_INT,0)!=(typeName.startsWith("qa")?7:8))throw new AssertionError("qualified type");unref.invokeExact(object);
      }
      for(var object:new MemorySegment[]{child,restored,protocol,transport,envelope,value})unref.invokeExact(object);
      System.out.println("{\"answer\":"+answer+",\"wire\":\""+HexFormat.of().formatHex(bytes.toArray(JAVA_BYTE))+"\"}");
    }
  }
}
