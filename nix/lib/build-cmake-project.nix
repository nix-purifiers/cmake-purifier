# SPDX-License-Identifier: MIT
#
# buildCMakeProject: builds and installs a CMake project in the sandbox
# from its cmake-purifier lockfile. It is a package for callPackage in the
# scope `pkgs.cmake-purifier`, which the flake's default package overlay
# adds to a package set. It takes the packages it builds with by name, so
# `pkgs.cmake-purifier.buildCMakeProject.override` replaces them.
#
#   { cmake-purifier }:
#   (cmake-purifier.buildCMakeProject { src = ./.; }).packages.<name>
#
# The package is stdenv.mkDerivation with nixpkgs' cmake setup hook, so
# every mkDerivation argument works as usual: `buildInputs` for the
# libraries find_package() looks for, and so on. The arguments of the
# builder itself:
#
# - `src`: the project.
# - `lockFile`: the lockfile, by default `cmake-purifier.lock.json` at the
#   root of `src`. A lockfile outside `src` is the one the build reads,
#   and a copy in `src` plays no part, so a packaging flake can lock a
#   project it does not change. When `src` is a path, evaluation fails
#   for a lockfile older than the project's build definition; for any
#   other `src`, the build fails before the configure.
# - `pname` and `version`: by default the name and version of the
#   top-level project(), which the lockfile records.
# - `cmakeFlags`: flags after the ones the lock run used, which come first
#   so that the build fetches nothing the lock run did not.
# - `fetchers`: fetchers that replace the ones the shared library's
#   fetchEntry and tree use, by name: `fetchurl`, `fetchgit`, `fetchhg`,
#   `fetchsvn` and `fetchcvs`. Each takes the arguments of the nixpkgs
#   fetcher of its name. They are the place for credentials and mirrors,
#   such as a fetchgit with a `netrcPhase` for a repository that needs a
#   login.
#
# Every download goes to the locked copy. FetchContent dependencies come
# from the initial cache that write-cache.sh writes, checkouts from the
# shims it installs, and every other download from mitm-cache, which
# its setup hook starts as the build's HTTP and HTTPS proxy, replaying the
# locked files. After the install, the build checks that every file the
# lockfile names is in the output.
#
# The result has four attributes, each known at evaluation time:
#
# - `packages.<pname>`: the installed project. Its passthru knows the
#   outputs from the lockfile, without a build: `installed."<path>"` is
#   each file the install writes, as a path in the output, by its path
#   relative to the install prefix, and `targets.<name>` is each
#   installed target, with its CMake `type` and the installed `files` of
#   its artifacts. `sources` is the sources of sources.nix.
# - `tests`: the same build with ctest run after it.
# - `release`: a directory with `<pname>-<version>-<system>.tar.gz`, the
#   installed project as a reproducible tarball, which
#   `cmake-purifier publish` uploads. Its programs and libraries refer to
#   the store paths of their runtime dependencies, like the outputs of
#   any Nix build.
# - `fetches`: the `entries` of the lock in memory (readLock, lock.nix),
#   the download entries of the shared library that the build fetches.
{
  lib,
  stdenv,
  cmake,
  git,
  mercurial,
  subversion,
  cvs,
  mitm-cache,
  gnutar,
  runCommand,
  callPackage,
  # The shared library's functions (lib.purifier of the purifier flake),
  # which the package overlay passes.
  purifier,
}:
{
  src,
  lockFile ? src + "/cmake-purifier.lock.json",
  fetchers ? { },
  cmakeFlags ? [ ],
  nativeBuildInputs ? [ ],
  preConfigure ? "",
  preCheck ? "",
  postInstall ? "",
  passthru ? { },
  ...
}@args:
let
  sources = callPackage ./sources.nix {
    inherit lockFile fetchers purifier;
    projectSrc = src;
  };
  inherit (sources) lock;
  # A tool the build checks out with, for the commands its shim passes on;
  # empty when the lockfile has no checkouts of it.
  realTool =
    tool: package: name:
    if (lock."${tool}Checkouts" or [ ]) != [ ] then "${package}/bin/${name}" else "";
  projectVersion = lock.project.version or "";
  pname = args.pname or lock.project.name;
  version = args.version or (if projectVersion == "" then "0" else projectVersion);
  outputs =
    if lock.outputs == null then
      {
        files = [ ];
        targets = { };
      }
    else
      lock.outputs;

  package = stdenv.mkDerivation (
    finalAttrs:
    removeAttrs args [
      "lockFile"
      "fetchers"
    ]
    // {
      inherit pname version src;
      nativeBuildInputs = [
        cmake
        mitm-cache
      ]
      ++ nativeBuildInputs;
      mitmCache = "${sources.tree}/http";
      cmakeFlags = lock.cmakeFlags ++ cmakeFlags;
      preConfigure = ''
        # mitm-cache is the proxy of the whole build, the tests included.
        # Requests to the machine itself, such as a test's own server, are
        # no downloads, and go around it.
        export no_proxy="localhost,127.0.0.1,::1" NO_PROXY="localhost,127.0.0.1,::1"
        if [ "$(bash ${./definition-hash.sh} .)" != ${lib.escapeShellArg lock.definitionHash} ]; then
          echo "cmake-purifier: ${toString lockFile} is older than the project: a CMakeLists.txt or *.cmake file changed since it was written. Run \`cmake-purifier lock\` to lock the project again." >&2
          exit 1
        fi
        bash ${./write-cache.sh} ${sources.tree} "$NIX_BUILD_TOP/cmake-purifier/sources" "$NIX_BUILD_TOP/cmake-purifier/cache.cmake" \
          ${../../cmake}/CMakePurifierLocked.cmake ${./.} ${git}/bin/git \
          "${realTool "hg" mercurial "hg"}" "${
            realTool "svn" subversion "svn"
          }" "${realTool "cvs" cvs "cvs"}"
        cmakeFlagsArray+=(-C "$NIX_BUILD_TOP/cmake-purifier/cache.cmake")
      ''
      # The ranlib of darwin, cctools' libtool, writes the ids of the build
      # user into an archive's symbol table, and a darwin build runs as
      # whichever build user is free. With -D it writes zeros, as llvm-ar
      # does for the members. CMake runs RANLIB on each archive it makes and
      # on its install, and the fixup again after strip.
      + lib.optionalString stdenv.hostPlatform.isDarwin ''
        printf '#!%s\nexec %q -D "$@"\n' "$BASH" "$(command -v "$RANLIB")" > "$NIX_BUILD_TOP/cmake-purifier/ranlib"
        chmod +x "$NIX_BUILD_TOP/cmake-purifier/ranlib"
        export RANLIB=$NIX_BUILD_TOP/cmake-purifier/ranlib
      ''
      + preConfigure;
      lockedOutputs = lib.concatMapStrings (f: "${f}\n") outputs.files;
      passAsFile = [ "lockedOutputs" ];
      # The lock run builds without running the tests, so the lockfile
      # holds no download of the tests. They run without mitm-cache as
      # their proxy and without the exceptions to it, so that a test of a
      # host that does not resolve, or of a proxy of its own, sees the
      # sandbox without a network.
      preCheck = ''
        unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY no_proxy NO_PROXY
      ''
      + preCheck;
      postInstall = postInstall + ''
        missing=0
        while IFS= read -r file; do
          if [ ! -e "$out/$file" ] && [ ! -L "$out/$file" ]; then
            echo "cmake-purifier: the lockfile names the output $file, which the install did not write. Run \`cmake-purifier lock\` again." >&2
            missing=1
          fi
        done < "$lockedOutputsPath"
        [ "$missing" = 0 ]
      '';
      passthru = passthru // {
        inherit sources;
        installed = lib.genAttrs outputs.files (file: "${finalAttrs.finalPackage}/${file}");
        targets = builtins.mapAttrs (
          _: target:
          target
          // {
            files = map (file: "${finalAttrs.finalPackage}/${file}") target.files;
          }
        ) outputs.targets;
      };
    }
  );
in
{
  packages.${pname} = package;

  tests = package.overrideAttrs {
    pname = "${pname}-tests";
    doCheck = true;
  };

  release =
    runCommand "${pname}-${version}-release"
      {
        nativeBuildInputs = [ gnutar ];
      }
      ''
        mkdir $out
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C ${package} -cf - . |
          gzip -9n > $out/${pname}-${version}-${stdenv.hostPlatform.system}.tar.gz
      '';

  fetches = sources.memory.entries;
}
