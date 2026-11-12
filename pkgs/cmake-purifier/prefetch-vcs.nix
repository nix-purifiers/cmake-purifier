# SPDX-License-Identifier: MIT
#
# The fetch of a Mercurial, Subversion or CVS artifact, for the lock run
# to learn its hash: `cmake-purifier lock` builds it with a hash that is
# wrong on purpose and reads the right one from the error. The artifact is
# the JSON of a lockfile entry without its `hash`, and the fetch is the
# shared library's fetchEntry with the fetchers of the sandbox build
# (sources.nix), so the hash is exactly the one that build checks.
#
# A repository in the store, which only tests have, is no input of the
# fetch by the URL alone, so the URL gets the store path's context here.
# builtins.storePath needs an impure evaluation, which the lock run's
# nix-build is.
{
  nixpkgs,
  # The source of the shared library.
  purifier,
  artifact,
}:
let
  pkgs = import nixpkgs { };
  inherit (pkgs) lib;
  purifierLib = import purifier { inherit lib; };
  withStore =
    text:
    let
      found = builtins.match "(.*)(/nix/store/[a-z0-9]{32}-[^/ ]*)(.*)" text;
    in
    if found == null then
      text
    else
      "${builtins.elemAt found 0}${builtins.storePath (builtins.elemAt found 1)}${builtins.elemAt found 2}";
  entry = builtins.fromJSON artifact;
  contextual =
    entry
    // lib.optionalAttrs (entry ? hg) {
      hg = entry.hg // {
        url = withStore entry.hg.url;
      };
    }
    // lib.optionalAttrs (entry ? svn) {
      svn = entry.svn // {
        url = withStore entry.svn.url;
      };
    }
    // lib.optionalAttrs (entry ? cvs) {
      cvs = entry.cvs // {
        cvsRoot = withStore entry.cvs.cvsRoot;
      };
    };
in
purifierLib.fetchEntry { inherit pkgs; } (contextual // { hash = lib.fakeHash; })
