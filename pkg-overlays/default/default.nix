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
# nix-build calls import. Both replay downloads with the library's
# replay server, the scope's `mitm-cache`, which serves a directory URL
# from its index.html, as an HTTP handler of the lock run lays out a page
# of a package index. The scope's `httpHandlers`, empty unless a project
# sets it, are the handlers the command's lock run applies.
{
  closure-lib,
  closure-inputs,
  ...
}:
{
  overlay = final: prev: {
    cmake-purifier = final.lib.makeScope final.newScope (self: {
      mitm-cache = closure-lib.purifier.replayServer { inherit (final) mitm-cache; };
      httpHandlers = [ ];
      cmake-purifier = self.callPackage ../../pkgs/cmake-purifier {
        purifier = closure-inputs.purifier;
        # Keep local CMake on PATH unless the scope explicitly selects an SDK.
        cmake = self.cmake or null;
      };
      buildCMakeProject = self.callPackage ../../pkgs/build-cmake-project/default.nix {
        inherit (closure-lib) purifier;
        composerPurifierSource = closure-inputs.composer-purifier;
      };
    });
  };
}
