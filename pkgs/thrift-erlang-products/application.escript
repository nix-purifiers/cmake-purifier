#!/usr/bin/env escript
%% SPDX-License-Identifier: MIT
main([Template, Name, Version, Ebin, RuntimeEbin]) ->
    case application:load(compiler) of
        ok -> ok;
        {error, {already_loaded, compiler}} -> ok
    end,
    {ok, CompilerVersion} = application:get_key(compiler, vsn),
    Beams = filelib:wildcard(filename:join(Ebin, "*.beam")),
    Compiled = [begin
        {ok, {Module, Chunks}} = beam_lib:chunks(File, [exports, imports, compile_info]),
        #{module => Module, file => File, chunks => Chunks}
    end || File <- Beams],
    Modules = lists:sort([maps:get(module, Item) || Item <- Compiled]),
    true = Modules =/= [],
    RuntimeModules = [begin
        {ok, {Module, _}} = beam_lib:chunks(File, [exports]),
        Module
    end || File <- filelib:wildcard(filename:join(RuntimeEbin, "*.beam")), RuntimeEbin =/= Ebin],
    [] = [Module || Module <- Modules, lists:member(Module, RuntimeModules)],
    {App, Properties} = case Template of
        "generated" ->
            {list_to_atom(Name), [{description, "Native generated Thrift Erlang bindings"},
              {vsn, Version}, {applications, [kernel, stdlib, thrift]}]};
        _ ->
            {ok, [{application, NativeApp, NativeProperties}]} = file:consult(Template),
            {vsn, NativeVersion} = lists:keyfind(vsn, 1, NativeProperties),
            {ok, ThriftCompilerVersion} = file:read_file(Version),
            true = string:trim(binary_to_list(ThriftCompilerVersion)) =:= "Thrift version " ++ NativeVersion,
            {NativeApp, NativeProperties}
    end,
    Terms = {application, App, lists:keystore(modules, 1, Properties, {modules, Modules})},
    ok = file:write_file(filename:join(Ebin, atom_to_list(App) ++ ".app"), io_lib:format("~p.~n", [Terms])),
    ok = file:write_file(filename:join(Ebin, "otp-observation.term"), io_lib:format("~p.~n", [
        #{format => "purifier-otp-production-v1",
          otp => erlang:system_info(otp_release), erts => erlang:system_info(version),
          architecture => erlang:system_info(system_architecture),
          nifVersion => erlang:system_info(nif_version),
          runtime => os:getenv("PURIFIER_ERLANG_RUNTIME"), runtimeRoot => code:root_dir(),
          compiler => code:which(compile), compilerPath => code:which(compile),
          compilerVersion => CompilerVersion, erlc => os:find_executable("erlc"),
          modules => Modules, compiled => Compiled}
    ])).
