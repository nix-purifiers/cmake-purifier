# SPDX-License-Identifier: MIT
# Read native Ruby parser output; generated source is never rewritten.
require 'ripper'
require 'json'

baseline_classes = ObjectSpace.each_object(Class).filter_map(&:name).to_h { |name| [name, true] }
baseline_constants = {}
ObjectSpace.each_object(Module) do |scope|
  next unless scope.name
  scope.constants(false).each { |name| baseline_constants[[scope.name == 'Object' ? nil : scope.name, name].compact.join('::')] = true }
end


def constant_path(node, scope)
  raise 'unsupported native constant declaration' unless node.is_a?(Array)
  case node[0]
  when :@const then scope + [node[1]]
  when :const_ref, :var_ref, :var_field then constant_path(node[1], scope)
  when :top_const_ref, :top_const_field then constant_path(node[1], [])
  when :const_path_ref, :const_path_field then constant_path(node[1], scope) + [node[2][1]]
  else raise 'unsupported native constant declaration'
  end
end

owned = {}
records = []
visit = nil
visit = lambda do |node, scope, program, file|
  return unless node.is_a?(Array)
  kind = node[0]
  if [:module, :class].include?(kind)
    path = constant_path(node[1], scope)
    name = path.join('::')
    if kind == :class
      raise "generated class collides with native Ruby/SDK class: #{name}" if baseline_classes[name]
      previous = owned[name]
      raise "native generated class collision: #{name}" if previous && previous != program
      owned[name] = program
    end
    records << { 'kind' => kind.to_s, 'name' => name, 'program' => program, 'file' => file }
    node[(kind == :class ? 3 : 2)..].each { |child| visit.call(child, path, program, file) }
  elsif kind == :assign && node[1].is_a?(Array) && [:var_field, :const_path_field, :top_const_field].include?(node[1][0])
    lhs = node[1]
    constant = lhs[0] != :var_field || lhs[1]&.first == :@const
    if constant
      name = constant_path(lhs, scope).join('::')
      raise "generated constant collides with native Ruby/SDK constant: #{name}" if baseline_constants[name]
      previous = owned[name]
      raise "native generated constant collision: #{name}" if previous && previous != program
      owned[name] = program
      records << { 'kind' => 'constant', 'name' => name, 'program' => program, 'file' => file }
    end
    visit.call(node[2], scope, program, file)
  else
    node.each { |child| visit.call(child, scope, program, file) if child.is_a?(Array) }
  end
end
JSON.parse(File.read(ARGV.fetch(0))).each do |entry|
  ast = Ripper.sexp(File.read(entry.fetch('file')))
  raise 'native Ruby parser rejected generated source' unless ast
  visit.call(ast, [], entry.fetch('program'), entry.fetch('file'))
end
File.write(ARGV.fetch(1), JSON.pretty_generate(records) + "\n")
