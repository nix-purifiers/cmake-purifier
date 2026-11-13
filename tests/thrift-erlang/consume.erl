-module(consume).
-export([main/0, read/2, read_exact/2, write/2, flush/1, close/1, handle_function/2, handle_error/2]).
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
    {ok, RpcTransport} = thrift_transport:new(?MODULE, #{role => client, input => <<>>, output => []}),
    {ok, RpcProtocol} = thrift_binary_protocol:new(RpcTransport),
    {ok, Client} = thrift_client:new(RpcProtocol, answer_service_thrift),
    {_, {ok, 43}} = thrift_client:call(Client, answer, [1]),
    io:format("answer=42 rpc=43 wire=~s runtime=~s generated=~s~n", [binary:encode_hex(Bytes), code:which(thrift_protocol), code:which(main_types)]),
    halt(0).

%% An in-memory duplex transport exercises the native client and processor
%% without requiring a listening socket inside the build sandbox.
write(State = #{output := Output}, Data) ->
    {State#{output => [Output, Data]}, ok}.

read(State = #{input := Input}, Length) when byte_size(Input) >= Length ->
    <<Result:Length/binary, Remaining/binary>> = Input,
    {State#{input => Remaining}, {ok, Result}};
read(State, _) -> {State, {error, closed}}.

read_exact(State, Length) -> read(State, Length).

flush(State = #{role := server, parent := Parent, output := Output}) ->
    Parent ! {rpc_response, self(), iolist_to_binary(Output)},
    {State#{output => []}, ok};
flush(State = #{role := client, output := Output}) ->
    Parent = self(),
    Request = iolist_to_binary(Output),
    {Pid, Monitor} = spawn_monitor(fun() ->
        Factory = fun() ->
            {ok, Transport} = thrift_transport:new(?MODULE,
                #{role => server, parent => Parent, input => Request, output => []}),
            thrift_binary_protocol:new(Transport)
        end,
        thrift_processor:init({self(), Factory, answer_service_thrift, ?MODULE})
    end),
    receive
        {rpc_response, Pid, Response} ->
            receive
                {'DOWN', Monitor, process, Pid, shutdown} ->
                    {State#{input => Response, output => []}, ok};
                {'DOWN', Monitor, process, Pid, Reason} -> erlang:error({processor_failed, Reason})
            after 5000 -> erlang:error(processor_did_not_stop)
            end;
        {'DOWN', Monitor, process, Pid, Reason} -> erlang:error({processor_failed, Reason})
    after 5000 -> erlang:error(processor_did_not_reply)
    end.

close(State) -> {State, ok}.
handle_function(answer, {Delta}) -> {reply, 42 + Delta}.
handle_error(undefined, closed) -> ok.
