# SPDX-License-Identifier: MIT
#
# The default package overlay. It adds one attribute to the package set,
# the scope `pkgs.cmake-purifier`, made with lib.makeScope. The scope holds
# the command `cmake-purifier` (pkgs/cmake-purifier) and the builder
# `buildCMakeProject` (pkgs/build-cmake-project/default.nix), each a
# callPackage package of the scope, so a package written for callPackage
# takes the scope by name:
#
#   { cmake-purifier }: (cmake-purifier.buildCMakeProject { src = ./.; }).packages.<name>
#
# `pkgs.cmake-purifier.overrideScope` replaces what the scope shares, and
# `.override` on the builder or the command replaces the packages it
# takes. A consumer that lists this flake in `projects` holds the overlay
# as `cmake-purifier/default`, which its package sets apply by default.
#
# Both use the shared library of the nix-purifiers: the builder its
# functions, and the command its source, which the command's own
# nix-build calls import.
{
  closure-lib,
  closure-inputs,
  ...
}:
{
  overlay = final: prev: {
    cmake-purifier = final.lib.makeScope final.newScope (self: {
      cmake-purifier = self.callPackage ../../pkgs/cmake-purifier {
        purifier = closure-inputs.purifier;
      };
      buildCMakeProject = self.callPackage ../../pkgs/build-cmake-project/default.nix {
        inherit (closure-lib) purifier;
      };
    });
  };
}
