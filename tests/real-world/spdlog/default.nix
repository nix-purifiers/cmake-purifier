# SPDX-License-Identifier: MIT
# Unmodified upstream spdlog with its compiled and header-only test suites.
# Enabling the suites downloads the upstream-selected Catch2 commit.
{ pkgs, buildCMakeProject }:
let
  src = pkgs.fetchFromGitHub {
    owner = "gabime";
    repo = "spdlog";
    rev = "6fa36017cfd5731d617e1a934f0e5ea9c4445b13"; # v1.15.3
    sha256 = "12m46hh59rgamr3qg3jyvxf5mkfj0c91ym4v0l79xqcqdps93cyj";
  };
  project = buildCMakeProject {
    inherit src;
    lockFile = ./cmake-purifier.lock.json;
  };
in
project // { inherit src; }
