import haxe.io.Bytes;
import org.apache.thrift.TConfiguration;
import org.apache.thrift.protocol.TBinaryProtocol;
import org.apache.thrift.transport.TMemoryStream;
import org.apache.thrift.transport.TStreamTransport;
class Handler implements AnswerService_service {
 public function new() {}
 public function answer(delta:haxe.Int32):haxe.Int32 { return 42+delta; }
}
class LoopbackTransport extends TStreamTransport {
 public var dispatch:Void->Void;
 public function new(input:TMemoryStream,output:TMemoryStream) {
  super(input,output,new TConfiguration());
 }
 public override function flush(callback:Dynamic->Void = null):Void {
  dispatch();
  if(callback!=null)callback(null);
 }
}
class Main {
 static function main() {
  final value=new Value();value.answer=42;
  final envelope=new Envelope();envelope.value=value;
  final memory=new TMemoryStream();
  envelope.write(new TBinaryProtocol(new TStreamTransport(memory,memory,new TConfiguration())));
  final size=memory.Position;memory.Position=0;
  final data=Bytes.alloc(size);memory.Read(data,0,size);
  final wire=data.toHex();
  final expected=Sys.args().length==0 ? "0c00010800010000002a0000" : Sys.args()[0];
  if(wire!=expected)throw 'wire '+wire;
  final decoded=new Envelope();
  final input=new TMemoryStream(data);
  decoded.read(new TBinaryProtocol(new TStreamTransport(input,null,new TConfiguration())));
  if(decoded.value.answer!=42)throw 'native decode';
  final request=new TMemoryStream();final response=new TMemoryStream();
  final clientTransport=new LoopbackTransport(response,request);
  final processor=new AnswerServiceProcessor(new Handler());
  clientTransport.dispatch=function() {
   request.Position=0;
   final server=new TStreamTransport(request,response,new TConfiguration());
   if(!processor.process(new TBinaryProtocol(server),new TBinaryProtocol(server)))throw 'processor';
   response.Position=0;
  };
  final client=new AnswerServiceImpl(new TBinaryProtocol(clientTransport));
  final answer=client.answer(1);
  if(answer!=43)throw 'native RPC '+answer;
  Sys.println(haxe.Json.stringify({answer:decoded.value.answer,rpc:answer,wire:wire}));
 }
}
