# cmake-purifier

cmake-purifier keeps CMake's development workflow on locked,
Nix-resolved dependencies. Use the normal build and test commands in your
working tree; building the project itself in the Nix sandbox is an
optional next step.

## Quickstart

From the project root:

```zsh
nix shell 'github:nix-purifiers/cmake-purifier#toolchain'
cmake-purifier lock
cmake-purifier prefetch
cmake -B build -C .cmake-purifier/initial-cache.txt
cmake --build build
ctest --test-dir build
```

Commit the lockfiles that the lock command writes, including the build
tool's own lockfile when it has one. Keep using the project's usual build,
test and editor commands with this setup. Nix provides the locked
dependencies; the development commands above run outside the Nix sandbox.
No project Nix files are needed for this workflow.

For downloads outside FetchContent, use the replay commands described in
[Development loop](#development-loop).

Sandboxed builds of the whole project are an optional
[next step](#building-the-project-with-nix).

For persistent use, add these packages through your usual Nix configuration.


## Development loop

Prefetch the locked downloads once, then work with CMake's own commands
on the initial cache that the prefetch writes:

```zsh
cmake-purifier prefetch
cmake -B build -C .cmake-purifier/initial-cache.txt
cmake --build build
ctest --test-dir build
```

The initial cache points FetchContent at copies of the locked sources and
git, hg, svn and cvs at the locked checkouts, and sets the configure
arguments of the lock run. A build directory configured with it keeps
those settings, so later runs of `cmake --build build` reconfigure with
them too.

A project that downloads files outside FetchContent, with `file(DOWNLOAD)`
or `ExternalProject_Add()` with a URL, runs the configure and the build
under `cmake-purifier replay --`, which starts mitm-cache as their HTTP
and HTTPS proxy, replaying the locked files:

```zsh
cmake-purifier replay -- cmake -B build -C \
  .cmake-purifier/initial-cache.txt
cmake-purifier replay -- cmake --build build
```

`prefetch` says when a project needs this. CMake makes these downloads
with its own HTTP client, some of them in `cmake -P` scripts that the
build runs, so only a proxy reaches them.

To add or upgrade a dependency, edit its `FetchContent_Declare()` (or its
`ExternalProject_Add()`, or its CPM.cmake call), run `cmake-purifier lock`
and `cmake-purifier prefetch` again, and configure again. A relock takes
about as long as a clean configure and build of the project.

`lock` keeps what the lockfile already resolved. A checkout whose ref
moves, such as a `GIT_TAG` that names a branch, a Subversion checkout at
HEAD, or a CVS checkout without a tag, stays at its locked revision.
`cmake-purifier update` moves such checkouts to where their refs point
now, and relocks with the configure arguments of the lockfile.
`cmake-purifier update <name>...` moves only the named FetchContent
dependencies or repositories.

## Building the project with Nix

Once the native development workflow is working, you can also build and
test the whole project in the Nix sandbox. For this step, keep a flake or
another Nix build definition in the project's repository, or maintain an
external packaging repository that points at its sources and lockfiles.
The builder consumes the same lockfiles as the development workflow.

The package is named after the top-level `project()`. Libraries that
`find_package()` looks for come from nixpkgs as usual, as `buildInputs =
[ pkgs.zlib ];` beside `src`.

A project whose authors want a flake packages itself with the same call,
in the project's repository or in another one:

```nix
{
  inputs.cmake-purifier.url =
    "github:nix-purifiers/cmake-purifier";
  inputs.nixpkgs.follows = "cmake-purifier/nixpkgs";

  outputs =
    { nixpkgs, cmake-purifier, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        overlays = [ cmake-purifier.overlays.default ];
      };
      project = pkgs.cmake-purifier.buildCMakeProject {
        src = ./.;
      };
    in
    {
      packages.${system}.default =
        project.packages.my-project;
      checks.${system}.tests = project.tests;
    };
}
```

The result has four attributes, each known at evaluation time:

- `packages.<name>` is the installed project, under the name of the
  top-level `project()`. Its `targets.<name>` and `installed."<path>"`
  name every output from the lockfile, without a build.
- `tests` is the same build with ctest run after it. The lock run does not
  run the tests, so the lockfile holds nothing that the tests download,
  and ctest runs without the replaying proxy: a test sees the sandbox
  without a network, as it expects of a host that does not resolve.
- `release` is a directory with the installed project as one
  reproducible tarball, which `cmake-purifier publish <tag> <installable>`
  uploads to a GitHub release with `gh`.
- `fetches` is the list of downloads, as entries of the shared library
  [purifier](https://github.com/nix-purifiers/purifier), for SBOM,
  license and vulnerability tools.

`buildCMakeProject` takes every argument of `stdenv.mkDerivation`, and
nixpkgs' CMake setup hook runs the build. `pkgs/build-cmake-project/default.nix`
documents the arguments of its own: `src`, `lockFile`, `cmakeFlags`
(after the locked ones), and `fetchers`. It takes the packages it builds
with by name, so `cmake-purifier.buildCMakeProject.override` replaces
them, and `pkgs.cmake-purifier.overrideScope` replaces what the scope
shares. A lockfile kept
outside `src`, as `lockFile`, is the one the build reads, so a packaging
flake can lock a project it does not change. Every command takes it as
`--lockfile <path>` or from the environment variable
`CMAKE_PURIFIER_LOCKFILE`, which the packaging flake's development shell
can set to the path it passes as `lockFile`.

`lib.cmake-purifier.readLock { src, lockFile ? … }` reads the lockfile
into the shape that every nix-purifier shares,
`{ purifier, entries, outputs, problems }`, for tools that read the locks
of every ecosystem, such as an SBOM generator.

### One-off builds without a project Nix file

For an ad hoc build, the builder can also be evaluated directly from the
project root. Replace the example package name with one from your project:

```zsh
nix build --impure --expr 'let
  purifier = builtins.getFlake "github:nix-purifiers/cmake-purifier";
  pkgs = import purifier.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ purifier.overlays.default ];
  };
in
(pkgs.cmake-purifier.buildCMakeProject { src = ./.; })
.packages.my-project'
```

This uses the purifier's pinned nixpkgs, matching the lock command above.
To build with ambient `<nixpkgs>` from your Nix search path instead,
replace `import purifier.inputs.nixpkgs` with `import <nixpkgs>`.
Both forms need no Nix files in your project. The build tool and language
versions must match the lockfile; with ambient nixpkgs, lock with the
purifier from that package set or pass a compatible toolchain to the builder.

## Working offline

`cmake-purifier prefetch` builds every download of the lockfile through
Nix and keeps it alive with a garbage-collector root,
`.cmake-purifier/sources-root`, beside the lockfile. After a prefetch, the
configure, the build, ctest and the editor work with the network cut off.
The directory `.cmake-purifier/` ignores itself in git.

`prefetch` realizes what the lockfile lists, and a CMake lockfile lists
only the project's downloads. The compilers, CMake itself and clangd come
from your toolchain. The `#toolchain` package supplies them through
`nix shell`.

## Editor

The initial cache sets `CMAKE_EXPORT_COMPILE_COMMANDS`, so the configure
writes `build/compile_commands.json`. clangd and other tools that read it
find every dependency's headers in the prefetched sources, offline. The
development shell of this flake has clangd; a project's own shell takes
`clang-tools` from nixpkgs.

## Troubleshooting

Each of these stops the command, the evaluation or the build with a
message that names the problem and the command that fixes it:

- **A dependency that the lockfile does not hold**, such as a new
  `FetchContent_Declare()`, a new ExternalProject repository or ref, or a
  new git clone: "the build declares the dependency …, which the lockfile
  does not hold. Run `cmake-purifier lock`".
- **A dependency whose declaration changed** without a change to the
  CMake files, such as a version from a `-D` argument: "the dependency …
  now declares the download …, but the lockfile holds …. Run
  `cmake-purifier lock`".
- **A lockfile older than the project.** The lockfile records a hash of
  every `CMakeLists.txt` and `*.cmake` file. When they hash differently,
  `prefetch`, the Nix evaluation (for a `src` that is a path) and the
  sandbox build stop: "… is older than the project … Run
  `cmake-purifier lock`".
- **A lockfile that was edited by hand.** The lockfile records the hash of
  its own content, and an edit, such as a changed hash of a download,
  stops the evaluation: "… was edited: its content no longer matches its
  contentHash".
- **An output that the sandbox build did not install**: "the lockfile
  names the output …, which the install did not write". The lock run
  builds with every program on your current `PATH`. A build that does
  more when it finds a program installs more in the lock run than in the
  sandbox. The build of curl is one such build: it writes its man pages
  when it finds Perl. Add the program to the inputs of the package and of
  the shell, and run `cmake-purifier lock` again.
- **A lockfile that is not valid JSON, or not a cmake-purifier lockfile**:
  the message names the file, and says to restore it from version control
  or run `cmake-purifier lock`.

## Supported language repositories

The lock run records downloads from HTTP and HTTPS servers, through
mitmproxy as the proxy of CMake and everything it runs, and from git,
Mercurial, Subversion and CVS repositories, through wrappers that CMake
finds as its `GIT_EXECUTABLE`, `HG_EXECUTABLE`,
`Subversion_SVN_EXECUTABLE` and `CVS_EXECUTABLE`. A checkout that names a
branch locks the commit the branch pointed at, and the next lock moves it.
A git repository cloned over SSH is locked by the HTTPS URL of the same
host, since the sandbox has no SSH credentials. `docs/development/product.md`
describes the lock run and the builds from the lockfile in full.

These are refused or unsupported:

- **A download by a program that ignores the proxy variables or
  `SSL_CERT_FILE`.** The recording and the replay both work as the proxy
  of everything the build runs. A program that opens its own connections,
  or trusts only a certificate store of its own, reaches neither. CMake,
  curl, git and most HTTP libraries honour both variables.
- **Requests other than GET.** A POST or another request with effects on
  the server has no response that is a fixed file, so the lockfile cannot
  hold it.
- **Two URLs that differ only in their query.** mitm-cache replays a URL
  from the path of its file, which carries no query, so the lock run
  refuses such a pair with an error that names both URLs.
- **A repository that needs a login**, with the default fetchers. The
  sandbox has no credentials. `buildCMakeProject` takes fetchers that
  have them in `fetchers`, such as nixpkgs' fetchgit with a `netrcPhase`
  as `fetchers.fetchgit`; a company mirror goes in `fetchers.fetchurl`.
- **CVS on aarch64-linux.** nixpkgs' cvs does not run on aarch64-linux, so
  a project with a CVS checkout locks and builds on x86_64-linux only.
- **Shared libraries across Linux and macOS.** `outputs` records the files
  of the lock run's install, and shared libraries have other names on each
  (`lib/libcpr.so` on Linux, `lib/libcpr.dylib` on macOS), so a project
  that installs them builds only on the OS its lockfile was locked on.
- **Version-control commands other than the checkout steps, on a locked
  checkout.** A locked checkout holds the files of its revision and no
  history, which keeps its hash reproducible. The shims answer the
  commands of a checkout and of its update steps, `git rev-parse`, and
  `git describe`. Any other command on a locked checkout, such as
  `git log` in a dependency's CMakeLists.txt, fails with a message that
  names it.

## Examples

For day-to-day work on these projects, use the native-tool setup and
commands in [Quickstart](#quickstart) and [Development loop](#development-loop).
The Nix expressions below show optional sandboxed packaging of those
projects.

### cpr

[cpr](https://github.com/libcpr/cpr) is a C++ HTTP library whose build
takes curl, zlib-ng, googletest and mongoose from FetchContent archives,
and libpsl from a FetchContent git checkout that it builds with meson. It
finds OpenSSL with `find_package()`, so locking it takes a shell with
OpenSSL besides the tools of its build. In a checkout of cpr, start that
shell, lock the project with its tests, and work on it:

```zsh
nix-shell -E '
  let
    purifier = builtins.getFlake "github:nix-purifiers/cmake-purifier";
    pkgs = import purifier.inputs.nixpkgs {
      system = builtins.currentSystem;
      overlays = [ purifier.overlays.default ];
    };
  in
  pkgs.mkShell {
    # curl writes its man pages when it finds Perl.
    nativeBuildInputs = [
      pkgs.cmake pkgs.perl pkgs.pkg-config pkgs.meson pkgs.ninja pkgs.python3
      pkgs.clang-tools pkgs.cmake-purifier.cmake-purifier
    ];
    buildInputs = [ pkgs.openssl ];
  }'
cmake-purifier lock -DCPR_BUILD_TESTS=ON
cmake-purifier prefetch
cmake -B build -C .cmake-purifier/initial-cache.txt
cmake --build build
ctest --test-dir build
```

Then build it with Nix from the same directory, with the same inputs:

```zsh
nix build --impure --expr 'let
  purifier = builtins.getFlake "github:nix-purifiers/cmake-purifier";
  pkgs = import purifier.inputs.nixpkgs {
    system = builtins.currentSystem;
    overlays = [ purifier.overlays.default ];
  };
in
(pkgs.cmake-purifier.buildCMakeProject {
  src = ./.;
  nativeBuildInputs = [
    pkgs.perl
    pkgs.pkg-config
    pkgs.meson
    pkgs.ninja
    pkgs.python3
  ];
  buildInputs = [ pkgs.openssl ];
}).packages.cpr'
```

cpr's tests need no network: they talk to a server that the tests start
on the machine itself. Its test suites each use the same port, so a
build that runs them sets `enableParallelChecking = false;` beside `src`.

## Native projections

Installed `SHARED_LIBRARY` targets expose `projections.native`,
`projections.python-ffi`, and `projections.java-ffi` on the builder result
and its package. Targets and paths come from native lock metadata. Static-only
projects have no FFI projections. Unsupported or ambiguous shared artifacts
fail when the projection is requested.

The catalog records producer identity, target system, library paths, headers
and pkg-config directories. Add the `python-ffi` view to `PYTHONPATH`, use
`purifier_native.load("target-name")`, and set ctypes signatures for its C API.
Java can load catalog paths through FFM or use the `java-ffi/java.args` library
path with existing JNI bindings. C++ requires compatible bindings; JNI is not
generated. Libraries retain their Nix runtime closure. The integration check
exercises ctypes, Java 21 FFM with preview enabled, and ordinary C/pkg-config,
including zlib's version and its actual loaded library path through `dladdr`.
Other systems are not implied by this local proof.

## Installed resources and schema bundles

Select installed public artifacts using `resourceRoots`, mapping public paths
to paths relative to the installation prefix. For example:

```nix
resourceRoots."." = "share/schemas";
resourceSchema = { format = "thrift"; entrypoints = [ "main.thrift" ]; };
```

The build result exposes `projections.resources`, `web`, and `java-resources`
alongside its existing native-library projections. The full installed package
exposes the same views. Use `.directory` as a compiler include root,
`.documentRoot` for static serving, and `.classPath` for Java resources at their
native paths. `resourceDependencies` can contribute other resource bundles;
collisions fail. Empty/default selections produce no resource projection.

Optional `resourceSchema` records native format and entrypoints. Select the
complete import/include tree; the adapter does not parse schemas or manufacture
language bindings. Existing project downloads and compiler/runtime choices stay
in their native inputs. A Thrift fixture installs a schema with a separate
included schema, compiles the projected tree with ordinary Thrift, round-trips a
message with its pinned Python runtime, and checks every selected resource over
HTTP and Java. Private installed siblings are excluded. Other formats may use
this resource mechanism but need their own native compiler/runtime validation.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

### Historical CMake

An explicitly selected `legacy-external-v1` profile has executed CMake
2.8.12.2 and 3.0.2 on x86_64 Linux. These are measured points, not a version
range. The default profile and format-3 locks keep the modern
FetchContent behavior. The historical profile records actual HTTP download
URLs and body hashes through the existing proxy, including downloads made
by nested `ExternalProject` builds. Native CMake performs its own
`URL_HASH` checks, extraction, dependency ordering, build, CTest and install.
It records the installed files from the native install manifest.

Supply the SDK as a derivation in the consumer's Nix source, with its source
archive identity, and select the same scope for the command and builder:

```nix
legacy = pkgs.cmake-purifier.overrideScope (_: _: {
  nativeProfile = "legacy-external-v1";
  cmake = cmake28;
  legacyProjectName = "my_project"; # The root project's exact native name.
  legacySdkAdapter = {
    version = 1;
    package = cmake28;
    moduleRoot = "share/cmake-2.8"; # Relative to this selected SDK.
    source = {
      url = "https://cmake.org/files/v2.8/cmake-2.8.12.2.tar.gz";
      sha256 = "8c6574e9afabcb9fc66f463bb1f2f051958d86c85c37fccf067eb1a44a120e5e";
    };
  };
});
# Use legacy.cmake-purifier in the development environment, and:
project = legacy.buildCMakeProject { src = ./.; };
```

The SDK must contain its real executable and module tree; a launcher that
runs another package's executable fails the startup identity check. The
command checks the native executable through `/proc`, its module root,
full version and root project. The adapter owns a safe relative module path
(`share/cmake-3.0` for the 3.0.2 fixture). Locks record that live scope's identity and never
reconstruct an SDK from a serialized path. Changing SDK scope requires a
new capture into a new `--lockfile`; an existing lock never silently changes
its SDK.

`lock -S <source>` runs the full native lifecycle. Configure definitions use
`-Dname=value`; their argument values are preserved. The measured SDKs cannot
persist newline definitions in their caches, so the profile rejects those
definitions.
Definitions replacing the observation or install context are also rejected.
`lock` keeps a previous lock intact on failure or changed bytes at a locked
URL; `update` explicitly accepts changed downloads after the native build
and hash checks pass. There is no named-dependency update selector.

`prefetch` fetches the observed archives through Nix. With the origin stopped,
use `replay -S <source> -- <command>` around the native configure/build/test
loop. Replay requires the prefetched tree to match the current lock.
`buildCMakeProject` uses the same selected SDK and locked archives in the Nix
sandbox, checks the install manifest, and provides an installed-tree release
archive. The profile requires a working native install target; it does not
provide `--no-build`, publishing, resource projections or extra configure
flags on the builder.

Historical locks have a separate closed format 4. They explicitly set
`dependencyMetadataAvailable = false` and `targetMetadataAvailable = false`:
observed downloads are an acquisition closure, not a named dependency
model. There is no File API target metadata; target/native projections fail
with an unavailable-metadata error. Installed file paths remain available.
No original publication-byte parity, arbitrary code confinement, general
proxy-bypass detection, additional SDK points, historical Darwin or a version range is
claimed. HTTPS also depends on the selected old SDK's native TLS support;
the repeatable legacy fixture exercises HTTP.

The consumer SDK recipe and repeatable original-source fixture are in
`tests/legacy-external`. They cover nested downloads, deterministic and
relocated relock, source preservation, native SDK origins at three levels,
installed consumers, cold replay, pure builds and failure controls.

### Generated FlatBuffers C++ packages

An installed FlatBuffers include tree can also produce a ready C++ package:

```nix
resourceRoots."." = "share/schemas";
resourceSchema = { format = "flatbuffers"; entrypoints = [ "main.fbs" ]; };
flatbuffersPackage = { name = "my_schemas"; version = "1.0.0"; };
```

The result exposes `packages.flatbuffers-bindings` and
`projections.flatbuffers-cpp`. CMake consumers use
`find_package(my_schemas 1.0 CONFIG REQUIRED)` and link `my_schemas::bindings`;
pkg-config consumers use `my_schemas`. Native `flatc` discovers the transitive
schema dependencies and generates headers with their include paths preserved.
The package propagates the same FlatBuffers SDK used for generation. Its
`flatbuffers-products.json` records compiler commands, native dependency rules,
and schema/header hashes. Resource dependencies join the selected schema tree
before generation. The original installed package keeps the same derivation
with or without `flatbuffersPackage`. The legacy profile rejects this option.
