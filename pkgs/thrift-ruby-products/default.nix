# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  ruby,
  thrift,
  purifier,
}:
{
  resources,
  thriftRubyPackage,
  thriftRubyDependencies ? [ ],
}:
let
  options = thriftRubyPackage;
  valid =
    builtins.isAttrs options
    &&
      builtins.attrNames options == [
        "name"
        "version"
      ]
    && builtins.isString options.name
    && options.name != ""
    && builtins.isString options.version
    && options.version != "";
  nativeRuntime = import ./runtime.nix { inherit runCommand ruby thrift; };
  runtime = nativeRuntime // {
    projections = purifier.rubygemsProjections {
      producer = nativeRuntime;
      archives = [
        {
          type = "generated-gem";
          producer = nativeRuntime;
          path = null;
        }
      ];
      dependencies = thriftRubyDependencies;
      inherit ruby runCommand;
    };
  };
  gem =
    runCommand "thrift-generated-ruby-gem"
      {
        outputs = [
          "out"
          "proof"
        ];
        nativeBuildInputs = [
          python3
          ruby
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          sdkSource = toString thrift.src;
          ruby = toString ruby;
          runtimeProof = "${nativeRuntime.proof}/runtime.json";
          bindingsTool = ./bindings.rb;
          packageTool = ./package.rb;
          inherit (options) name version;
        };
        passAsFile = [ "spec" ];
        passthru = {
          schemaResources = resources;
          sdk = thrift;
          sdkRuntime = runtime;
        };
      }
      ''
        export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
        mkdir -p "$HOME" "$proof"
        python ${./generate.py} "$specPath" "$out" "$proof"
      '';
in
assert valid || throw "cmake-purifier: thriftRubyPackage requires an explicit gem name and version";
gem
// {
  projections = purifier.rubygemsProjections {
    producer = gem;
    archives = [
      {
        type = "generated-gem";
        producer = gem;
        path = null;
      }
    ];
    dependencies = [ runtime ];
    inherit ruby runCommand;
  };
}
