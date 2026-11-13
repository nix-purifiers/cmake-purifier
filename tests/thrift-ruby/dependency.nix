# SPDX-License-Identifier: MIT
{ pkgs, purifier }:
let
  capture = builtins.fromJSON (builtins.readFile ./logger-capture.json);
  archive = pkgs.fetchurl {
    inherit (capture) url;
    hash = builtins.convertHash {
      hash = capture.sha256;
      hashAlgo = "sha256";
      toHashFormat = "sri";
    };
  };
in
archive
// {
  projections = purifier.rubygemsProjections {
    producer = archive;
    archives = [
      {
        type = "generated-gem";
        producer = archive;
        path = null;
      }
    ];
    ruby = pkgs.ruby;
    inherit (pkgs) runCommand;
  };
}
