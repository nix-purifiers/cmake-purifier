{ pkgs, build }:
let
  changed = pkgs.runCommand "thrift-ocaml-field2" { } ''
    cp -r ${./fixtures/thrift-cpp} "$out"
    chmod -R u+w "$out"
    sed -i 's/1: value.Value/2: value.Value/' "$out/schemas/main.thrift"
  '';
  package =
    src:
    (build {
      inherit src;
      lockFile = ./fixtures/thrift-cpp/cmake-purifier.lock.json;
      pname = "thrift-ocaml-schema";
      version = "1.0.0";
      resourceRoots."." = "share/schemas";
      resourceSchema = {
        format = "thrift";
        entrypoints = [ "main.thrift" ];
      };
      thriftOCamlPackage.oasis = ./thrift-ocaml/_oasis;
    }).packages.thrift-ocaml-bindings;
  first = package ./fixtures/thrift-cpp;
  second = package changed;
  consumer =
    product: field: mode:
    let
      view = product.projections.ocaml;
      inherit (product) scope;
    in
    pkgs.runCommand "ordinary-native-thrift-ocaml-consumer-${mode}-${toString field}"
      {
        nativeBuildInputs = [
          scope.ocaml
          scope.findlib
          pkgs.stdenv.cc
        ];
      }
      ''
        mkdir "$out" work
        cp ${./thrift-ocaml/consume.ml} work/consume.ml
        cd work
        export OCAMLPATH="${view.findlibPath}:${view.runtimeFindlibPath}"
        ocamlfind ${
          if mode == "native" then "ocamlopt" else "ocamlc"
        } -thread -package example-thrift -linkpkg consume.ml -o "$out/consumer"
        "$out/consumer" ${toString field} > "$out/consumer.txt"
        cp ${product.proof}/native-ocaml.json "$out/native-package.json"
      '';
  a = consumer first 1 "native";
  b = consumer second 2 "native";
  c = consumer first 1 "byte";
  d = consumer second 2 "byte";
  collision =
    (package (
      pkgs.runCommand "invalid-native-ocaml-output-collision" { } ''
        cp -r ${./fixtures/thrift-cpp} "$out"
        chmod -R u+w "$out"
        printf '\nservice AnswerService {i32 duplicate()}\n' >> "$out/schemas/common/value.thrift"
      ''
    )).schemaResources;

in
pkgs.runCommand "native-thrift-ocaml-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      first.scope.ocaml
      first.scope.findlib
    ];
    controls = builtins.toJSON {
      source = toString first.source;
      proof = toString first.proof;
      package = toString first;
      observation = builtins.fromJSON (builtins.unsafeDiscardStringContext first.observation);
      generation = builtins.fromJSON (builtins.unsafeDiscardStringContext first.source.spec);
      generator = ../pkgs/thrift-ocaml-products/generate.py;
      observer = ../pkgs/thrift-ocaml-products/observe.py;
      inspector = "${first.proof}/native-inspect";
      cases = [
        {
          resources = toString collision;
          diagnostic = "native generated OCaml output collision";
        }
      ];
    };
    nativeInputs = first.observation + first.source.spec;
    passAsFile = [ "controls" ];
  }
  ''
    mkdir "$out"
    cp -r ${a} "$out/first-native"
    cp -r ${b} "$out/second-native"
    cp -r ${c} "$out/first-byte"
    cp -r ${d} "$out/second-byte"
    python3 ${./thrift-ocaml/controls.py} "$controlsPath" "$out/rejections.json"
  ''
