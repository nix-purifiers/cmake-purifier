# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  python3,
  thrift,
  purifier,
}:
{ resources, thriftDocumentation }:
let
  formats =
    thriftDocumentation.formats or [
      "html"
      "markdown"
    ];
  webjar = thriftDocumentation.webjar or null;
  generated =
    runCommand "thrift-native-documentation"
      {
        nativeBuildInputs = [
          python3
          thrift
        ];
        spec = builtins.toJSON {
          resources = toString resources;
          sdk = toString thrift;
          inherit formats;
        };
        passAsFile = [ "spec" ];
      }
      ''
        python ${./generate.py} "$specPath" "$out"
        mkdir -p "$out/assets"
        ${lib.concatMapStringsSep "\n" (format: ''cp -r "$out/${format}" "$out/assets/${format}"'') formats}
      '';
  views = purifier.resourceProjections {
    producer = generated;
    roots."." = "assets";
    inherit runCommand python3;
  };
  publication = lib.optionalAttrs (webjar != null) (
    purifier.webjarProjections (
      webjar
      // {
        producer = generated;
        assets = "${generated}/assets";
        inherit runCommand python3;
      }
    )
  );
in
assert
  builtins.isAttrs thriftDocumentation
  && lib.all (
    name:
    lib.elem name [
      "formats"
      "webjar"
    ]
  ) (builtins.attrNames thriftDocumentation);
assert
  builtins.isList formats
  && formats != [ ]
  && builtins.length (lib.unique formats) == builtins.length formats
  && lib.all (
    f:
    lib.elem f [
      "html"
      "markdown"
      "gv"
      "mmd"
    ]
  ) formats;
generated // { projections = views // publication; }
