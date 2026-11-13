# SPDX-License-Identifier: MIT
require 'rubygems/package'
require 'fileutils'
require 'json'
require 'digest'

archive, proof, source, compiler, ruby = ARGV
package = Gem::Package.new(archive)
package.verify
spec = package.spec
version = File.read(File.join(proof, 'compiler-version.txt')).strip
raise 'native Ruby runtime does not match selected Thrift compiler' unless version == "Thrift version #{spec.version}"
source = File.realpath(source)
extracted = File.join(proof, 'native-gem-files')
package.extract_files(extracted)
files = package.contents.sort.map do |name|
  original = File.realpath(File.join(source, name))
  raise 'native gem member escapes SDK source' unless original.start_with?(source + '/')
  packed = File.join(extracted, name)
  raise 'native gem changed SDK file bytes' unless File.binread(original) == File.binread(packed)
  { 'file' => name, 'sha256' => Digest::SHA256.file(original).hexdigest }
end
File.write(File.join(proof, 'runtime.json'), JSON.pretty_generate({
  'format' => 'purifier-thrift-ruby-runtime-v1',
  'compiler' => compiler, 'compilerVersion' => version,
  'source' => source, 'ruby' => ruby, 'rubyVersionObservation' => RUBY_DESCRIPTION,
  'name' => spec.name, 'version' => spec.version.to_s,
  'nativeGemspecSha256' => Digest::SHA256.file(File.join(source, 'thrift.gemspec')).hexdigest,
  'gemSha256' => Digest::SHA256.file(archive).hexdigest,
  'runtimeDependencies' => spec.runtime_dependencies.map { |dep| { 'name' => dep.name, 'requirement' => dep.requirement.to_s } },
  'files' => files
}) + "\n")
