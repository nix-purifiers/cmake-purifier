// SPDX-License-Identifier: MIT
package consumer;
import proof.main.Envelope;
import proof.main.AnswerService;
import proof.common.Value;
import org.apache.thrift.protocol.TBinaryProtocol;
import org.apache.thrift.transport.TMemoryBuffer;
import org.apache.thrift.transport.TMemoryInputTransport;
import java.nio.file.*;
import java.util.Arrays;
import java.util.HexFormat;
public class Consumer {
  public static void main(String[] args) throws Exception {
    var expected=HexFormat.of().parseHex(args[0]);var decoded=new Envelope();decoded.read(new TBinaryProtocol(new TMemoryInputTransport(expected)));
    if(decoded.getValue().getAnswer()!=42)throw new AssertionError("C++wire");
    var out=new TMemoryBuffer(256);new Envelope(new Value(42)).write(new TBinaryProtocol(out));var bytes=Arrays.copyOf(out.getArray(),out.length());Files.write(Path.of(args[1]),bytes);
    var request=new TMemoryBuffer(256);var response=new TMemoryBuffer(256);var client=new AnswerService.Client(new TBinaryProtocol(response),new TBinaryProtocol(request));client.send_answer(42);var processor=new AnswerService.Processor<AnswerService.Iface>(delta->delta+1);processor.process(new TBinaryProtocol(request),new TBinaryProtocol(response));int answer=client.recv_answer();if(answer!=43)throw new AssertionError("RPC");
    if(new proof.a.Value(7).getAnswer()!=7 || new proof.b.Value(8).getAnswer()!=8)throw new AssertionError("qualified native types");
    String own=Path.of(Envelope.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();String sdk=Path.of(org.apache.thrift.TBase.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();
    System.out.println("42:"+HexFormat.of().formatHex(bytes));System.out.println(answer);System.out.println(own);System.out.println(sdk);System.out.println("7:8");
  }
}
