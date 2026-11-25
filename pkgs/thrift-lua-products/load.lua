-- Verify native SDK/global ownership without rewriting generated Lua code.
local module_catalog, trace_file = arg[1], arg[2]
local original_pairs, original_type, original_error = pairs, type, error
local original_tostring, original_sort = tostring, table.sort
local original_ipairs, original_require, original_globals = ipairs, require, _G
local original_open, original_assert = io.open, assert
local original_concat, original_print = table.concat, print
local module_trace = {}
for index, searcher in ipairs(package.searchers) do
  package.searchers[index] = function(name)
    local loader, origin = searcher(name)
    if original_type(loader)=='function' and original_type(origin)=='string' then
      module_trace[#module_trace+1] = name .. '\t' .. origin
    end
    return loader, origin
  end
end
local sdk, generated = {}, {}
for line in io.lines(module_catalog) do
  local kind, name = line:match('^(%S+)\t(.+)$')
  if kind=='sdk' then sdk[#sdk+1]=name else generated[#generated+1]=name end
end
for _, name in original_ipairs(sdk) do original_require(name) end
local native_loaded={}
for key,value in pairs(package.loaded) do native_loaded[key]=value end
local snapshot, visited, known = {}, {}, {}
local function capture(object, path)
  if original_type(object)~='table' or visited[object] then return end
  visited[object]=true
  known[object]=known[object] or {}
  for key,value in original_pairs(object) do
    if not known[object][key] then
      snapshot[#snapshot+1]={object=object,key=key,value=value,path=path..'.'..original_tostring(key)}
      known[object][key]=true
    end
    if original_type(value)=='table' then capture(value,path..'.'..original_tostring(key)) end
  end
end
capture(original_globals,'native')
local globals={}
for name in original_pairs(original_globals) do globals[#globals+1]=name end
original_sort(globals)
for _, name in original_ipairs(generated) do
  if native_loaded[name]~=nil then original_error('generated Lua module shadows original runtime: '..name) end
  original_require(name)
  for _, row in original_ipairs(snapshot) do
    if row.object[row.key]~=row.value then
      original_error('generated Lua global shadows original or earlier native binding: '..row.path)
    end
  end
  -- New generated bindings become authoritative before loading another module.
  visited={}
  capture(original_globals,'native')
end
local trace=original_assert(original_open(trace_file,'w'))
trace:write(original_concat(module_trace,'\n'),'\n')
trace:close()
original_print('native original SDK and generated Lua bindings loaded')
