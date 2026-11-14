# SPDX-License-Identifier: MIT
require 'json'
require 'rbconfig'
require 'thrift'
gem 'thrift-ruby-proof'
require 'root/root_types'
require 'root/answer_service'
extension_suffix = '/thrift_native.' + RbConfig::CONFIG.fetch('DLEXT')
raise 'native extension missing' unless $LOADED_FEATURES.any? { |path| path.end_with?(extension_suffix) }
original = Root::Pair.new(left: First::Value.new(answer: 7), right: Second::Value.new(answer: 8))
wire = Thrift::Serializer.new.serialize(original)
decoded = Root::Pair.new
Thrift::Deserializer.new.deserialize(decoded, wire)
raise 'qualified classes aliased' unless decoded.left.class == First::Value && decoded.right.class == Second::Value && First::Value != Second::Value
raise 'qualified values lost' unless [decoded.left.answer, decoded.right.answer] == [7, 8]
request = Thrift::MemoryBufferTransport.new
response = Thrift::MemoryBufferTransport.new
client = Root::AnswerService::Client.new(Thrift::BinaryProtocol.new(response), Thrift::BinaryProtocol.new(request))
handler = Object.new
def handler.answer(delta); 42 + delta; end
def handler.base_answer(delta); 41 + delta; end
client.send_answer(1)
client.send_base_answer(1)
processor = Root::AnswerService::Processor.new(handler)
2.times { processor.process(Thrift::BinaryProtocol.new(request), Thrift::BinaryProtocol.new(response)) }
rpc = client.recv_answer
inherited = client.recv_base_answer
raise 'qualified or inherited RPC failed' unless rpc == 43 && inherited == 42
puts JSON.generate({values: [decoded.left.answer, decoded.right.answer], classes: [decoded.left.class.name, decoded.right.class.name], wire: wire.unpack1('H*'), rpc: rpc, inherited: inherited})
