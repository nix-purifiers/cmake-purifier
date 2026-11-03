# SPDX-License-Identifier: MIT
#
# The flake's checks. Every one builds in the sandbox; the only network
# access is the fixed-output fetches of locked downloads.
#
# The `conformance-*` checks are the ones the purifier contract names.
# `conformance-relock`, `conformance-rebuild` and `conformance-offline`
# need Nix or the network outside the sandbox, so they are jobs of the CI
# workflow (.github/workflows/check.yml) instead.
{
  pkgs,
  # The shared library's functions.
  purifier,
  # buildCMakeProject of the flake's package overlay, and
  # lib.cmake-purifier.readLock.
  buildCMakeProject,
  readLock,
  cmake-purifier,
}:
let
  inherit (pkgs) lib;

  # The fixture builds the way a consumer's package does: through the
  # buildCMakeProject of the package overlay.
  basic = buildCMakeProject {
    src = ./fixtures/basic;
  };
  basicPackage = basic.packages.purifier-basic;

  # Downloads outside FetchContent_MakeAvailable(): file(DOWNLOAD) at
  # configure and build time, CPM.cmake, and ExternalProject_Add() with a
  # URL and with git.
  extras =
    (buildCMakeProject {
      src = ./fixtures/extras;
    }).packages.purifier-extras;

  # Checkouts from Subversion, Mercurial, git with submodules and CVS, of
  # repositories the checks build themselves. CVS has a fixture of its
  # own, which only x86_64-linux builds.
  vcsRepos = import ./vcs-repos.nix { inherit pkgs; };
  vcs =
    (buildCMakeProject {
      src = ./fixtures/vcs;
      inherit (vcsRepos) fetchers;
    }).packages.purifier-vcs;
  cvs =
    (buildCMakeProject {
      src = ./fixtures/cvs;
      inherit (vcsRepos) fetchers;
    }).packages.purifier-cvs;

  # The basic fixture's lockfile, and a lockfile made from it, with the
  # contentHash that `cmake-purifier lock` would write.
  basicLockFile = ./fixtures/basic/cmake-purifier.lock.json;
  basicLock = lib.importJSON basicLockFile;
  writeLock =
    name: body:
    let
      content = removeAttrs body [ "contentHash" ];
    in
    # builtins.toFile, since the builder reads the lockfile at evaluation,
    # where a build output would be import-from-derivation.
    builtins.toFile name (
      builtins.toJSON (
        content // { contentHash = "sha256:" + builtins.hashString "sha256" (builtins.toJSON content); }
      )
    );

  # A copy of the basic fixture with a shell command applied, as a
  # derivation, so that the build rather than the evaluation reads it.
  basicWith =
    name: edit:
    pkgs.runCommand name { } ''
      cp -r ${./fixtures/basic} $out
      chmod -R u+w $out
      ${edit}
    '';

  # A build of a copy of the basic fixture that must fail with output
  # that matches <pattern>.
  buildFails =
    name:
    {
      src,
      lockFile ? basicLockFile,
      pattern,
    }:
    pkgs.runCommand name
      {
        failed =
          pkgs.testers.testBuildFailure
            (buildCMakeProject { inherit src lockFile; }).packages.purifier-basic;
      }
      ''
        grep -q -- ${lib.escapeShellArg pattern} $failed/testBuildFailure.log || {
          echo "${name}: the build failed without '${pattern}':" >&2
          cat $failed/testBuildFailure.log >&2
          exit 1
        }
        touch $out
      '';

  # Reading <lockFile> for a copy of <src> with nix/lib/lock.nix must fail
  # at evaluation, with an error that matches <pattern>: the evaluation
  # fails with the lock's problems, as the shared library's checkLock
  # does. It runs inside the sandbox, on a dummy store, from copies of the
  # library and of the source, since only builtins are needed.
  evalFails =
    name:
    {
      lockFile,
      src ? null,
      edit ? "",
      pattern,
    }:
    pkgs.runCommand name { nativeBuildInputs = [ pkgs.nix ]; } ''
      export HOME=$TMPDIR NIX_STATE_DIR=$TMPDIR/state NIX_CONF_DIR=$TMPDIR
      cp -r ${../nix/lib} lib
      cp ${lockFile} lock.json
      ${lib.optionalString (src != null) ''
        cp -r ${src} project
        chmod -R u+w project
        ${edit}
      ''}
      if nix-instantiate --store dummy:// --eval --strict -E \
        "let lock = import $PWD/lib/lock.nix { lockFile = $PWD/lock.json; ${
          lib.optionalString (src != null) "src = $PWD/project;"
        } }; in if lock.problems == [ ] then lock.purifier else throw (builtins.concatStringsSep \"\n\" lock.problems)" > log 2>&1; then
        echo "${name}: the evaluation succeeded" >&2
        exit 1
      fi
      grep -q -- ${lib.escapeShellArg pattern} log || {
        echo "${name}: the evaluation failed without '${pattern}':" >&2
        cat log >&2
        exit 1
      }
      touch $out
    '';

  # The command that fixes a broken lockfile, as every error names it.
  relock = "cmake-purifier lock";
in
{
  basic = basicPackage;

  # ctest runs the doctest suite, which includes the header that the lock
  # records as a download FetchContent does not extract.
  basic-tests = basic.tests;

  # The installed program runs, with fmt and argparse from the lockfile.
  basic-runs = pkgs.runCommand "basic-runs" { } ''
    out_text=$(${basicPackage}/bin/greet --name purifier)
    [ "$out_text" = "Hello, purifier!" ] || { echo "greet printed: $out_text" >&2; exit 1; }
    touch $out
  '';

  # The package name and version come from the lockfile's project().
  basic-name = pkgs.runCommand "basic-name" { } ''
    [ ${basicPackage.pname} = purifier-basic ] && [ ${basicPackage.version} = 1.2.3 ]
    touch $out
  '';

  # The outputs come from the lockfile at evaluation time: the target
  # greet and the file it installs, with no build needed to know them.
  # fmt installs itself as part of the fixture, so its static library is
  # an output too.
  basic-outputs =
    assert basicPackage.targets.greet.type == "EXECUTABLE";
    assert basicPackage.targets.greet.files == [ "${basicPackage}/bin/greet" ];
    assert basicPackage.targets.fmt.files == [ "${basicPackage}/lib/libfmt.a" ];
    assert builtins.elem "include/fmt/format.h" (builtins.attrNames basicPackage.installed);
    pkgs.runCommand "basic-outputs" { } ''
      [ "$(${builtins.head basicPackage.targets.greet.files} --name outputs)" = "Hello, outputs!" ]
      touch $out
    '';

  # The release is the installed project as one tarball, with the program
  # in it.
  basic-release = pkgs.runCommand "basic-release" { } ''
    tarball=${basic.release}/purifier-basic-1.2.3-${pkgs.stdenv.hostPlatform.system}.tar.gz
    tar -tzf $tarball > listing
    grep -qx './bin/greet' listing
    touch $out
  '';

  # `fetches` is the lockfile's artifacts, so an SBOM tool reads the
  # downloads without the lockfile's format.
  basic-fetches =
    assert basic.fetches == basicLock.artifacts;
    assert builtins.all (entry: entry ? hash) basic.fetches;
    pkgs.runCommand "basic-fetches" { } "touch $out";

  # readLock gives the lock in memory of the contract, which the shared
  # library's checkLock accepts, with the outputs under the project's name.
  read-lock =
    let
      lock = purifier.checkLock (readLock {
        src = ./fixtures/basic;
      });
    in
    assert lock.purifier == "cmake-purifier";
    assert lock.entries == basicLock.artifacts;
    assert builtins.attrNames lock.outputs == [ "purifier-basic" ];
    assert lock.problems == [ ];
    assert (readLock { lockFile = ./fixtures/basic/cmake-purifier.lock.json; }).problems == [ ];
    pkgs.runCommand "read-lock" { } "touch $out";

  inherit extras;

  # Every installed file of extras is an output, the license the build
  # downloaded included.
  extras-outputs =
    assert extras.targets.extras.files == [ "${extras}/bin/extras" ];
    assert
      builtins.attrNames extras.installed == [
        "bin/extras"
        "share/purifier-extras/fmt-LICENSE"
      ];
    pkgs.runCommand "extras-outputs" { } ''
      grep -q 'Victor Zverovich' ${extras.installed."share/purifier-extras/fmt-LICENSE"}
      touch $out
    '';

  # The program runs with argparse and cxxopts from CPM.cmake, zlib from
  # an ExternalProject archive and expected-lite from an ExternalProject
  # checkout, and the license the build downloaded is installed.
  extras-runs = pkgs.runCommand "extras-runs" { } ''
    out_text=$(${extras}/bin/extras --count 5)
    [ "$out_text" = "count 5, zlib 1.3.1" ] || { echo "extras printed: $out_text" >&2; exit 1; }
    grep -q 'Copyright (c) 2012 - present, Victor Zverovich' ${extras}/share/purifier-extras/fmt-LICENSE
    touch $out
  '';

  # The repositories of the vcs fixture, which tests/relock-fixtures.sh
  # builds to lock the fixture against.
  vcs-repos = vcsRepos.repos;

  inherit vcs;

  # The program runs with a header from each repository: the Subversion one
  # through FetchContent, the Mercurial and CVS ones through
  # ExternalProject_Add(), and one from each submodule that a
  # GIT_SUBMODULES list keeps. The fixture itself fails to configure or to
  # build when a checkout holds a submodule its list leaves out.
  vcs-runs = pkgs.runCommand "vcs-runs" { } ''
    out_text=$(${builtins.head vcs.targets.vcs.files})
    [ "$out_text" = "svn hg sub_a sub_b" ] || { echo "vcs printed: $out_text" >&2; exit 1; }
    touch $out
  '';

  # The URL rules of the lock run (lock/urls.py), the mapping of SSH URLs
  # to HTTPS ones included.
  lock-urls = pkgs.runCommand "lock-urls" { } ''
    ${pkgs.python3}/bin/python3 -I ${../lock/test_urls.py} ${../lock}
    touch $out
  '';

  # The reading of the lock run's records (lock/records.py), on sample
  # records of each kind.
  lock-records = pkgs.runCommand "lock-records" { } ''
    ${pkgs.python3}/bin/python3 -I ${../lock/test_records.py} ${../lock}
    touch $out
  '';

  # The shell and the Nix definition hash agree on every fixture, and
  # both match the lockfile, so that neither check fails a fixture that
  # did not change.
  definition-hash =
    let
      fixtures = {
        basic = ./fixtures/basic;
        extras = ./fixtures/extras;
        vcs = ./fixtures/vcs;
        cvs = ./fixtures/cvs;
      };
    in
    pkgs.runCommand "definition-hash" { } (
      lib.concatStrings (
        lib.mapAttrsToList (name: src: ''
          [ "$(bash ${../nix/lib/definition-hash.sh} ${src})" = ${import ../nix/lib/definition-hash.nix src} ] ||
            { echo "${name}: the shell and the Nix definition hash differ" >&2; exit 1; }
          [ ${import ../nix/lib/definition-hash.nix src} = ${
            (lib.importJSON (src + "/cmake-purifier.lock.json")).definitionHash
          } ] ||
            { echo "${name} hashes differently from its lockfile" >&2; exit 1; }
        '') fixtures
      )
      + "touch $out\n"
    );

  # A lockfile older than the project fails: at evaluation when `src` is a
  # path, and before the configure when it is a derivation.
  conformance-stale =
    let
      edit = "echo '# an edit' >> project/lib/CMakeLists.txt";
      atEvaluation = evalFails "conformance-stale-evaluation" {
        lockFile = basicLockFile;
        src = ./fixtures/basic;
        inherit edit;
        pattern = "is older than the project: a CMakeLists.txt or \\*.cmake file changed since it was written. Run `${relock}`";
      };
      atBuild = buildFails "conformance-stale-build" {
        src = basicWith "basic-stale" "echo '# an edit' >> $out/lib/CMakeLists.txt";
        pattern = "is older than the project: a CMakeLists.txt or \\*.cmake file changed since it was written. Run `${relock}`";
      };
    in
    pkgs.runCommand "conformance-stale" { inherit atEvaluation atBuild; } "touch $out";

  # A lockfile whose hash of a download was edited fails, since its
  # content no longer matches its contentHash.
  conformance-tampered = evalFails "conformance-tampered" {
    lockFile = pkgs.writeText "tampered.json" (
      builtins.toJSON (
        basicLock
        // {
          artifacts = map (
            a: a // { hash = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="; }
          ) basicLock.artifacts;
        }
      )
    );
    pattern = "was edited: its content no longer matches its contentHash.";
  };

  # A lockfile without the dependency fmt, which the build declares,
  # fails at the configure.
  conformance-missing = buildFails "conformance-missing" {
    src = ./fixtures/basic;
    lockFile = writeLock "missing.json" (
      basicLock // { dependencies = builtins.filter (d: d.name != "fmt") basicLock.dependencies; }
    );
    # CMake wraps the message, so the check matches its first line.
    pattern = "cmake-purifier: the build declares the dependency fmt, which the lockfile";
  };

  # A lockfile that is not valid JSON fails, and so does valid JSON that
  # is not a cmake-purifier lockfile; both errors name the command.
  conformance-malformed =
    let
      invalid = evalFails "conformance-malformed-json" {
        lockFile = pkgs.writeText "invalid.json" ''{ "version": 3,'';
        pattern = "run `${relock}` to write it again";
      };
      incomplete = evalFails "conformance-malformed-keys" {
        lockFile = pkgs.writeText "incomplete.json" ''{ "version": 3 }'';
        pattern = "is not a cmake-purifier lockfile: it has no project, definitionHash";
      };
    in
    pkgs.runCommand "conformance-malformed" { inherit invalid incomplete; } "touch $out";

  # The basic fixture builds from its lockfile kept outside `src`, which
  # holds no lockfile of its own.
  conformance-external =
    let
      external = buildCMakeProject {
        src = lib.fileset.toSource {
          root = ./fixtures/basic;
          fileset = lib.fileset.difference ./fixtures/basic basicLockFile;
        };
        lockFile = basicLockFile;
      };
      package = external.packages.purifier-basic;
    in
    pkgs.runCommand "conformance-external" { } ''
      [ ! -e ${package.src}/cmake-purifier.lock.json ]
      [ "$(${package}/bin/greet --name external)" = "Hello, external!" ]
      touch $out
    '';

  # A real-world project: libcpr/cpr, built from a lockfile kept in
  # tests/real-world/cpr, with its test suites run. The lockfile records
  # the outputs of one platform, and cpr installs shared libraries, whose
  # names differ off Linux (libcpr.so on Linux, libcpr.dylib on macOS), so
  # it builds on Linux only.
  real-world-cpr =
    if pkgs.stdenv.hostPlatform.isLinux then
      (import ./real-world/cpr {
        inherit pkgs buildCMakeProject;
      }).tests
    else
      pkgs.runCommand "real-world-cpr-skipped" { } ''
        echo "cmake-purifier: real-world-cpr is skipped on ${pkgs.stdenv.hostPlatform.system}, where cpr's shared libraries have other names than the Linux ones its lockfile records" >&2
        touch $out
      '';

  # The source and the development shell that tests/relock-fixtures.sh
  # locks cpr with.
  real-world-cpr-src =
    (import ./real-world/cpr {
      inherit pkgs buildCMakeProject;
    }).src;
  real-world-cpr-shell =
    (import ./real-world/cpr {
      inherit pkgs buildCMakeProject cmake-purifier;
    }).shell;

  nix-library = import ./nix-library.nix { inherit pkgs purifier; };

  # The command builds, which runs shellcheck on it.
  inherit cmake-purifier;
}
// (
  if vcsRepos.cvsWorks then
    {
      inherit cvs;
      # The program runs with the header of the CVS checkout.
      cvs-runs = pkgs.runCommand "cvs-runs" { } ''
        [ "$(${builtins.head cvs.targets.cvs.files})" = cvs ]
        touch $out
      '';
    }
  else
    {
      # nixpkgs' cvs aborts on this system, in the 2006 gnulib vasnprintf
      # it bundles, so the CVS fixture builds on x86_64-linux only.
      cvs = pkgs.runCommand "cvs-skipped" { } ''
        echo "cmake-purifier: the CVS fixture is skipped on ${pkgs.stdenv.hostPlatform.system}, where nixpkgs' cvs aborts" >&2
        touch $out
      '';
    }
)
