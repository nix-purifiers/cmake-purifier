import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:thrift/thrift.dart';
import 'package:main/main.dart' as schema;
import 'package:value/value.dart' as common;

class Handler implements schema.AnswerService {
  Future<int> answer(int delta) async => 42 + delta;
}

class ResponseBuffer extends TBufferedTransport {
  final completed = Completer<void>();
  Future flush() async {
    await super.flush();
    completed.complete();
  }
}

class RequestBuffer extends TBufferedTransport {
  late void Function() dispatch;
  final ResponseBuffer response;
  RequestBuffer(this.response);
  Future flush() async {
    await super.flush();
    dispatch();
    await response.completed.future.timeout(Duration(seconds: 5));
  }
}

Future<void> main(List<String> args) async {
  final expected = args.single;
  final original = schema.Envelope()..value = (common.Value()..answer = 42);
  final bytes = TSerializer().write(original);
  final hex = bytes.map((n) => n.toRadixString(16).padLeft(2, '0')).join();
  if (hex != expected) throw StateError('native Dart/C++ wire mismatch: $hex');
  final input = Uint8List.fromList([
    for (var i = 0; i < expected.length; i += 2)
      int.parse(expected.substring(i, i + 2), radix: 16)
  ]);
  final decoded = schema.Envelope();
  TDeserializer().read(decoded, input);
  if (decoded.value?.answer != 42) throw StateError('native Dart decode');
  final response = ResponseBuffer();
  final request = RequestBuffer(response);
  final processor = schema.AnswerServiceProcessor(Handler());
  request.dispatch = () {
    if (!processor.process(TBinaryProtocol(request), TBinaryProtocol(response))) {
      throw StateError('native generated processor rejected request');
    }
  };
  final client = schema.AnswerServiceClient(TBinaryProtocol(response), TBinaryProtocol(request));
  final answer = await client.answer(1);
  if (answer != 43) throw StateError('native generated RPC result: $answer');
  print(jsonEncode({'answer': decoded.value?.answer, 'rpc': answer, 'wire': hex}));
}
