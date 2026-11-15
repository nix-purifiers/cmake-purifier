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
  nativeProfile ? "modern-v1",
  legacyProjectName ? null,
  legacySdkAdapter ? null,
  stdenv,
  cmake,
  git,
  mercurial,
  subversion,
  cvs,
  mitm-cache,
  gnutar,
  runCommand,
  python3,
  callPackage,
  # The shared library's functions (lib.purifier of the purifier flake),
  # which the package overlay passes.
  purifier,
}:
{
  src,
  lockFile ? src + "/cmake-purifier.lock.json",
  fetchers ? { },
  resourceRoots ? { },
  resourceDependencies ? [ ],
  resourceSchema ? null,
  flatbuffersPackage ? null,
  flatbuffersRustPackage ? null,
  flatbuffersRustRuntimeLock ? null,
  flatbuffersRustVendorBuilder ? null,
  flatbuffersRustProjector ? null,
  flatbuffersPythonPackage ? null,
  flatbuffersJavaPackage ? null,
  flatbuffersJavaRuntimeBuilder ? null,
  capnprotoPackage ? null,
  thriftPackage ? null,
  thriftCGLibPackage ? null,
  thriftCGLibRuntimeBuilder ? null,
  thriftJavaPackage ? null,
  thriftJavaRuntimeLock ? null,
  thriftJavaRuntimeWrapper ? null,
  thriftJavaRuntimeBuilder ? null,
  flatbuffersTypeScriptPackage ? null,
  flatbuffersTypeScriptVendorBuilder ? null,
  flatbuffersTypeScriptWebjar ? null,
  flatbuffersGoPackage ? null,
  flatbuffersGoProjector ? null,
  flatbuffersGoRuntimeModulePath ? null,
  thriftDocumentation ? null,
  thriftJavaScriptPackage ? null,
  thriftJavaScriptRuntimeBuilder ? null,
  thriftJavaScriptDependencies ? [ ],
  thriftJavaScriptBrowserBuilder ? null,
  thriftJavaScriptWebjar ? null,
  thriftRustPackage ? null,
  thriftRustRuntimeLock ? null,
  thriftRustVendorBuilder ? null,
  thriftRustProjector ? null,
  thriftGoPackage ? null,
  thriftGoProjector ? null,
  thriftPythonPackage ? null,
  thriftRubyPackage ? null,
  thriftRubyDependencies ? [ ],
  cmakeFlags ? [ ],
  nativeBuildInputs ? [ ],
  preConfigure ? "",
  preCheck ? "",
  postInstall ? "",
  passthru ? { },
  ...
}@args:
if nativeProfile == "legacy-external-v1" then
  callPackage ./legacy-build-cmake-project.nix {
    inherit
      cmake
      purifier
      legacyProjectName
      legacySdkAdapter
      ;
  } args
else if nativeProfile != "modern-v1" then
  throw "cmake-purifier: unknown nativeProfile ${nativeProfile}"
else
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

    flatbuffers = callPackage ../flatbuffers-products { } {
      resources = resourceViews.resources;
      inherit flatbuffersPackage;
    };
    capnproto = callPackage ../capnproto-products { } {
      resources = resourceViews.resources;
      inherit capnprotoPackage;
    };
    thrift = callPackage ../thrift-products { } {
      resources = resourceViews.resources;
      inherit thriftPackage;
    };
    thriftCGLib = callPackage ../thrift-c-glib-products { } {
      resources = resourceViews.resources;
      inherit thriftCGLibPackage thriftCGLibRuntimeBuilder;
    };
    thriftJava = callPackage ../thrift-java-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit
        thriftJavaPackage
        thriftJavaRuntimeLock
        thriftJavaRuntimeWrapper
        thriftJavaRuntimeBuilder
        ;
    };
    thriftPython = callPackage ../thrift-python-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit thriftPythonPackage;
    };
    thriftRuby = callPackage ../thrift-ruby-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit thriftRubyPackage thriftRubyDependencies;
    };
    flatbuffersPython = callPackage ../flatbuffers-python-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit flatbuffersPythonPackage;
    };
    flatbuffersJava = callPackage ../flatbuffers-java-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit flatbuffersJavaPackage flatbuffersJavaRuntimeBuilder;
    };
    flatbuffersTypeScript = callPackage ../flatbuffers-typescript-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit flatbuffersTypeScriptPackage flatbuffersTypeScriptVendorBuilder flatbuffersTypeScriptWebjar;
    };
    flatbuffersGo = callPackage ../flatbuffers-go-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit flatbuffersGoPackage flatbuffersGoProjector flatbuffersGoRuntimeModulePath;
    };
    thriftDocs = callPackage ../thrift-documentation-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit thriftDocumentation;
    };
    thriftJavaScript = callPackage ../thrift-javascript-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit
        thriftJavaScriptPackage
        thriftJavaScriptRuntimeBuilder
        thriftJavaScriptDependencies
        thriftJavaScriptBrowserBuilder
        thriftJavaScriptWebjar
        ;
    };
    thriftGo = callPackage ../thrift-go-products { inherit purifier; } {
      resources = resourceViews.resources;
      inherit thriftGoPackage thriftGoProjector;
    };
    thriftRust = callPackage ../thrift-rust-products { } {
      resources = resourceViews.resources;
      inherit
        thriftRustPackage
        thriftRustRuntimeLock
        thriftRustVendorBuilder
        thriftRustProjector
        ;
    };
    flatbuffersRust = callPackage ../flatbuffers-rust-products { } {
      resources = resourceViews.resources;
      inherit
        flatbuffersRustPackage
        flatbuffersRustRuntimeLock
        flatbuffersRustVendorBuilder
        flatbuffersRustProjector
        ;
    };
    resourceViews = lib.optionalAttrs (resourceRoots != { }) (
      purifier.resourceProjections {
        producer = package;
        roots = resourceRoots;
        dependencies = resourceDependencies;
        schema = resourceSchema;
        inherit runCommand python3;
      }
    );

    schemaJvm =
      lib.optionalAttrs
        (
          (thriftDocumentation != null && (thriftDocumentation.webjar or null) != null)
          || flatbuffersJavaPackage != null
          || thriftJavaPackage != null
          || (flatbuffersTypeScriptPackage != null && flatbuffersTypeScriptWebjar != null)
          || (thriftJavaScriptPackage != null && thriftJavaScriptWebjar != null)
        )
        (
          purifier.jvmProjections {
            producer = package;
            repository = null;
            dependencies =
              lib.optional (flatbuffersJavaPackage != null) flatbuffersJava
              ++ lib.optional (thriftJavaPackage != null) thriftJava
              ++ lib.optional (
                flatbuffersTypeScriptPackage != null && flatbuffersTypeScriptWebjar != null
              ) flatbuffersTypeScript
              ++ lib.optional (thriftJavaScriptPackage != null && thriftJavaScriptWebjar != null) thriftJavaScript
              ++ lib.optional (
                thriftDocumentation != null && (thriftDocumentation.webjar or null) != null
              ) thriftDocs;
            formats = [
              "maven"
              "ivy"
            ];
            inherit runCommand python3;
          }
        );
    projections =
      (purifier.nativeTargetProjections {
        producer = package;
        targets = outputs.targets;
        installedFiles = outputs.files;
        system = stdenv.hostPlatform.system;
        inherit runCommand python3;
      })
      // resourceViews
      // lib.optionalAttrs (thriftDocumentation != null) { thrift-documentation = thriftDocs; }
      // lib.optionalAttrs (flatbuffersPackage != null) { flatbuffers-cpp = flatbuffers; }
      // lib.optionalAttrs (capnprotoPackage != null) { capnproto-cpp = capnproto; }
      // lib.optionalAttrs (thriftPackage != null) { thrift-cpp = thrift; }
      // lib.optionalAttrs (thriftCGLibPackage != null) { thrift-c-glib = thriftCGLib; }
      // lib.optionalAttrs (thriftPythonPackage != null) thriftPython.projections
      // lib.optionalAttrs (thriftRubyPackage != null) thriftRuby.projections
      // lib.optionalAttrs (flatbuffersPythonPackage != null) flatbuffersPython.projections
      // schemaJvm
      // lib.optionalAttrs (flatbuffersTypeScriptPackage != null) {
        npm = flatbuffersTypeScript.projections.npm;
      }
      // lib.optionalAttrs (flatbuffersGoPackage != null) flatbuffersGo.projections
      // lib.optionalAttrs (thriftGoPackage != null) thriftGo.projections
      // lib.optionalAttrs (flatbuffersRustPackage != null) flatbuffersRust.projections
      // lib.optionalAttrs (thriftJavaScriptPackage != null) thriftJavaScript.projections
      // lib.optionalAttrs (thriftRustPackage != null) thriftRust.projections;

    package = stdenv.mkDerivation (
      finalAttrs:
      removeAttrs args [
        "lockFile"
        "fetchers"
        "resourceRoots"
        "resourceDependencies"
        "resourceSchema"
        "flatbuffersPackage"
        "flatbuffersRustPackage"
        "flatbuffersRustRuntimeLock"
        "flatbuffersRustVendorBuilder"
        "flatbuffersRustProjector"
        "flatbuffersPythonPackage"
        "flatbuffersJavaPackage"
        "flatbuffersJavaRuntimeBuilder"
        "capnprotoPackage"
        "thriftPackage"
        "thriftCGLibPackage"
        "thriftCGLibRuntimeBuilder"
        "thriftJavaPackage"
        "thriftJavaRuntimeLock"
        "thriftJavaRuntimeWrapper"
        "thriftJavaRuntimeBuilder"
        "flatbuffersTypeScriptPackage"
        "flatbuffersTypeScriptVendorBuilder"
        "flatbuffersTypeScriptWebjar"
        "flatbuffersGoPackage"
        "flatbuffersGoProjector"
        "flatbuffersGoRuntimeModulePath"
        "thriftDocumentation"
        "thriftJavaScriptPackage"
        "thriftJavaScriptRuntimeBuilder"
        "thriftJavaScriptBrowserBuilder"
        "thriftJavaScriptWebjar"
        "thriftJavaScriptDependencies"
        "thriftRustPackage"
        "thriftRustRuntimeLock"
        "thriftRustVendorBuilder"
        "thriftRustProjector"
        "thriftGoPackage"
        "thriftGoProjector"
        "thriftPythonPackage"
        "thriftRubyPackage"
        "thriftRubyDependencies"
      ]
      // lib.optionalAttrs stdenv.buildPlatform.isDarwin {
        # Replay listens only on loopback. Keep external outbound networking denied
        # by the Nix sandbox, and preserve an explicit caller override.
        __darwinAllowLocalNetworking = args.__darwinAllowLocalNetworking or true;
      }
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
          inherit sources projections;
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
  assert
    thriftDocumentation == null
    || (resourceRoots != { } && pname != "thrift-documentation")
    || throw "cmake-purifier: Thrift documentation requires captured resources and a distinct project name";
  assert
    flatbuffersPackage == null
    || (resourceRoots != { } && pname != "flatbuffers-bindings")
    || throw "cmake-purifier: flatbuffersPackage requires resourceRoots and a project name other than flatbuffers-bindings";
  assert
    capnprotoPackage == null
    || (resourceRoots != { } && pname != "capnproto-bindings")
    || throw "cmake-purifier: capnprotoPackage requires resourceRoots and a project name other than capnproto-bindings";
  assert
    thriftPackage == null
    || (resourceRoots != { } && pname != "thrift-bindings")
    || throw "cmake-purifier: thriftPackage requires resourceRoots and a project name other than thrift-bindings";
  assert
    thriftCGLibPackage == null
    || (resourceRoots != { } && pname != "thrift-c-glib-bindings")
    || throw "cmake-purifier: Thrift C GLib requires captured resources and a distinct project name";
  assert
    thriftJavaPackage == null
    || (resourceRoots != { } && pname != "thrift-java-bindings")
    || throw "cmake-purifier: thriftJavaPackage requires resourceRoots and a distinct project name";
  assert
    thriftPythonPackage == null
    || (resourceRoots != { } && pname != "thrift-python-bindings")
    || throw "cmake-purifier: thriftPythonPackage requires resourceRoots and a project name other than thrift-python-bindings";
  assert
    thriftRubyPackage == null
    || (resourceRoots != { } && pname != "thrift-ruby-bindings")
    || throw "cmake-purifier: thriftRubyPackage requires captured resources and a distinct project name";
  assert
    flatbuffersPythonPackage == null
    || (resourceRoots != { } && pname != "flatbuffers-python-bindings" && thriftPythonPackage == null)
    || throw "cmake-purifier: flatbuffersPythonPackage requires resourceRoots, a distinct project name, and its own Python projection";
  assert
    flatbuffersJavaPackage == null
    || (resourceRoots != { } && pname != "flatbuffers-java-bindings")
    || throw "cmake-purifier: flatbuffersJavaPackage requires resourceRoots and a distinct project name";
  assert
    flatbuffersTypeScriptPackage == null
    || (
      resourceRoots != { }
      && pname != "flatbuffers-typescript-bindings"
      && thriftJavaScriptPackage == null
    )
    || throw "cmake-purifier: FlatBuffers TypeScript requires resourceRoots, a distinct project name and its own npm projection";
  assert
    flatbuffersGoPackage == null
    || (resourceRoots != { } && pname != "flatbuffers-go-bindings" && thriftGoPackage == null)
    || throw "cmake-purifier: flatbuffersGoPackage requires resourceRoots, a distinct name and its own Go projection";
  assert
    thriftGoPackage == null
    || (resourceRoots != { } && pname != "thrift-go-bindings")
    || throw "cmake-purifier: thriftGoPackage requires resourceRoots and a distinct project name";
  assert
    flatbuffersRustPackage == null
    || (resourceRoots != { } && pname != "flatbuffers-rust-bindings" && thriftRustPackage == null)
    || throw "cmake-purifier: flatbuffersRustPackage requires resourceRoots, a distinct project name and its own Rust projection";
  assert
    thriftJavaScriptPackage == null
    || (resourceRoots != { } && pname != "thrift-javascript-bindings")
    || throw "cmake-purifier: thriftJavaScriptPackage requires resourceRoots and a distinct project name";
  assert
    thriftRustPackage == null
    || (resourceRoots != { } && pname != "thrift-rust-bindings")
    || throw "cmake-purifier: thriftRustPackage requires resourceRoots and a distinct project name";
  {
    packages = {
      ${pname} = package;
    }
    // lib.optionalAttrs (flatbuffersPackage != null) { flatbuffers-bindings = flatbuffers; }
    // lib.optionalAttrs (capnprotoPackage != null) { capnproto-bindings = capnproto; }
    // lib.optionalAttrs (thriftPackage != null) { thrift-bindings = thrift; }
    // lib.optionalAttrs (thriftCGLibPackage != null) { thrift-c-glib-bindings = thriftCGLib; }
    // lib.optionalAttrs (thriftJavaPackage != null) { thrift-java-bindings = thriftJava; }
    // lib.optionalAttrs (thriftPythonPackage != null) { thrift-python-bindings = thriftPython; }
    // lib.optionalAttrs (thriftRubyPackage != null) { thrift-ruby-bindings = thriftRuby; }
    // lib.optionalAttrs (flatbuffersPythonPackage != null) {
      flatbuffers-python-bindings = flatbuffersPython;
    }
    // lib.optionalAttrs (flatbuffersJavaPackage != null) {
      flatbuffers-java-bindings = flatbuffersJava;
    }
    // lib.optionalAttrs (flatbuffersTypeScriptPackage != null) {
      flatbuffers-typescript-bindings = flatbuffersTypeScript;
    }
    // lib.optionalAttrs (flatbuffersGoPackage != null) { flatbuffers-go-bindings = flatbuffersGo; }
    // lib.optionalAttrs (thriftGoPackage != null) { thrift-go-bindings = thriftGo; }
    // lib.optionalAttrs (thriftDocumentation != null) { thrift-documentation = thriftDocs; }
    // lib.optionalAttrs (thriftJavaScriptPackage != null) {
      thrift-javascript-bindings = thriftJavaScript;
    }
    // lib.optionalAttrs (thriftRustPackage != null) { thrift-rust-bindings = thriftRust; }
    // lib.optionalAttrs (flatbuffersRustPackage != null) {
      flatbuffers-rust-bindings = flatbuffersRust;
    };
    inherit projections;

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
