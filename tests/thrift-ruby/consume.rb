# SPDX-License-Identifier: MIT
require 'json'
require 'digest'
require 'thrift'
gem 'thrift-ruby-proof'
require 'main_types'
require 'value_types'
require 'answer_service'
raise 'native Thrift extension missing' unless $LOADED_FEATURES.any? { |path| path.end_with?('/thrift_native.so') }
wire = Thrift::Serializer.new.serialize(Envelope.new(value: Value.new(answer: 42)))
decoded = Envelope.new
Thrift::Deserializer.new.deserialize(decoded, wire)
raise 'native Ruby roundtrip failed' unless decoded.value.answer == 42
request = Thrift::MemoryBufferTransport.new
response = Thrift::MemoryBufferTransport.new
client = AnswerService::Client.new(Thrift::BinaryProtocol.new(response), Thrift::BinaryProtocol.new(request))
handler = Object.new
def handler.answer(delta); 42 + delta; end
client.send_answer(1)
AnswerService::Processor.new(handler).process(Thrift::BinaryProtocol.new(request), Thrift::BinaryProtocol.new(response))
rpc = client.recv_answer
raise 'native Ruby RPC failed' unless rpc == 43
package = Gem::Specification.find_by_name('thrift-ruby-proof')
runtime = Gem::Specification.find_by_name('thrift')
files = Dir.glob('lib/**/*.rb', base: package.full_gem_path).sort.to_h do |path|
  [path.delete_prefix('lib/'), Digest::SHA256.file(File.join(package.full_gem_path, path)).hexdigest]
end
origins = $LOADED_FEATURES.select { |path| path.end_with?('/main_types.rb', '/value_types.rb', '/answer_service.rb', '/thrift_native.so') }
raise 'generated Ruby loaded outside installed schema gem' unless origins.select { |path| path.end_with?('.rb') }.all? { |path| path.start_with?(package.full_gem_path + '/') }
raise 'extension loaded outside installed runtime gem' unless origins.select { |path| path.end_with?('.so') }.all? { |path| path.start_with?(runtime.full_gem_path + '/') }
puts JSON.generate({answer: decoded.value.answer, rpc: rpc, wire: wire.unpack1('H*'),
  version: package.version.to_s, runtimeVersion: runtime.version.to_s, files: files, origins: origins})
