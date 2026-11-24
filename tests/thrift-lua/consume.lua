local loaded = {}
for index, searcher in ipairs(package.searchers) do
  package.searchers[index] = function(name)
    local loader, origin = searcher(name)
    if type(loader)=='function' and type(origin)=='string' then
      loaded[#loaded+1] = name .. '\t' .. origin
    end
    return loader, origin
  end
end
local main_prefix = arg[2] or 'main'
local value_prefix = arg[3] or 'value'
local expected_field = tonumber(arg[4]) or 1
require(value_prefix .. '_ttypes')
require(main_prefix .. '_ttypes')
require(main_prefix .. '_AnswerService')
require 'TMemoryBuffer'
require 'TBinaryProtocol'
local memory = TMemoryBuffer:new{}
local protocol = TBinaryProtocol:new{trans=memory}
Envelope:new{value=Value:new{answer=42}}:write(protocol)
local wire = memory:getBuffer()
local hex = wire:gsub('.', function(c) return string.format('%02x',string.byte(c)) end)
assert(hex==string.format('0c%04x0800010000002a0000',expected_field), hex)
local decoded = Envelope:new{}
decoded:read(protocol)
assert(decoded.value.answer==42)
local request, response = TMemoryBuffer:new{}, TMemoryBuffer:new{}
local client = AnswerServiceClient:new{
  iprot=TBinaryProtocol:new{trans=response},oprot=TBinaryProtocol:new{trans=request}
}
local processor = AnswerServiceProcessor:new{handler={answer=function(self, delta) return 42+delta end}}
client:send_answer(1)
processor:process(TBinaryProtocol:new{trans=request},TBinaryProtocol:new{trans=response})
assert(client:recv_answer(1)==43)
local trace = assert(io.open(arg[1],'w'))
trace:write(table.concat(loaded,'\n'),'\n')
trace:close()
print('original Thrift Lua native wire42/RPC43 ' .. hex)
