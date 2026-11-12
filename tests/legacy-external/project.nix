# SPDX-License-Identifier: MIT
{
  fixtureRoot,
  sdkVersion ? "2.8.12.2",
}:
let
  tools = import ./tools.nix { inherit sdkVersion; };
  src = builtins.path {
    path = builtins.toPath fixtureRoot;
    name = "legacy-native-fixture";
    filter = path: type: builtins.baseNameOf path != ".cmake-purifier";
  };
  project = tools.scope.buildCMakeProject { inherit src; };
in
{
  package = project.packages.legacy_native;
  inherit (project) tests release projections;
  targets = project.packages.legacy_native.targets;
  memory = import ../../lib-overlays/default/lock.nix {
    inherit src;
    lockFile = src + "/cmake-purifier.lock.json";
  };
}
