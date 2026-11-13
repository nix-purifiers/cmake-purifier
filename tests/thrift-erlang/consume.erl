-module(consume).
-export([main/0]).
-include_lib("schema/include/main_types.hrl").

main() ->
    {ok, Started} = application:ensure_all_started(schema),
    true = lists:member(schema, Started),
    true = lists:member(thrift, Started),
    {ok, RuntimeVersion} = application:get_key(thrift, vsn),
    ExpectedCompiler = "Thrift version " ++ RuntimeVersion,
    ExpectedCompiler = os:getenv("EXPECTED_COMPILER_VERSION"),
    true = lists:prefix(os:getenv("EXPECTED_APP_ROOT") ++ "/", code:which(main_types)),
    true = lists:prefix(os:getenv("EXPECTED_RUNTIME_ROOT") ++ "/", code:which(thrift_protocol)),
    Value = #'Envelope'{value = #'Value'{answer = 42}},
    {ok, File} = file:open("wire.bin", [raw, write, binary]),
    {ok, Transport} = thrift_file_transport:new(File),
    {ok, Protocol} = thrift_binary_protocol:new(Transport),
    {Written, ok} = thrift_protocol:write(Protocol, {{struct, {main_types, 'Envelope'}}, Value}),
    {Flushed, ok} = thrift_protocol:flush_transport(Written),
    {_, ok} = thrift_protocol:close_transport(Flushed),
    {ok, Bytes} = file:read_file("wire.bin"),
    Expected = binary:decode_hex(list_to_binary(os:getenv("EXPECTED_WIRE"))),
    Expected = Bytes,
    {ok, Input} = thrift_memory_buffer:new(Bytes),
    {ok, Reader} = thrift_binary_protocol:new(Input),
    {_, {ok, Value}} = thrift_protocol:read(Reader, {struct, {main_types, 'Envelope'}}),
    {struct, [{1, i32}]} = answer_service_thrift:function_info(answer, params_type),
    i32 = answer_service_thrift:function_info(answer, reply_type),
    io:format("answer=42 wire=~s runtime=~s generated=~s~n", [binary:encode_hex(Bytes), code:which(thrift_protocol), code:which(main_types)]),
    halt(0).
