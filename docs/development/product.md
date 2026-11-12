# Product

cmake-purifier is one of the nix-purifiers: a plugin and a Nix library per
build tool, which record the files the tool wants to download in a
lockfile, so that Nix can build the project in its sandbox without
generated Nix files in the project.

CMake has no single download channel, so the lock run records downloads
at the channels every CMake download goes through: HTTP and HTTPS,
through a recording proxy, and the version-control tools, through
`GIT_EXECUTABLE`, `HG_EXECUTABLE`, `Subversion_SVN_EXECUTABLE` and
`CVS_EXECUTABLE`. A
dependency provider adds which FetchContent dependency each download
belongs to. CMake 3.24 added dependency providers and
`CMAKE_PROJECT_TOP_LEVEL_INCLUDES`, which inject one without edits to the
project, so the purifier needs CMake 3.24 or newer. The README describes
the use and the limits; this file describes the mechanism.

cmake-purifier meets the purifier contract, `CONTRACT.md` of
[purifier](https://github.com/nix-purifiers/purifier). CMake has no
lockfile of its own, so `cmake-purifier.lock.json` records every
download. The pins a project writes, such as a `URL_HASH`, are arguments
in CMake code that only a configure evaluates, so Nix evaluation cannot
read them.

## The lock run

`cmake-purifier lock` runs the configure, the build and an install into a
scratch prefix with three recorders:

- mitmproxy, as the HTTP and HTTPS proxy of CMake and everything it
  runs, with its certificate authority in `SSL_CERT_FILE`. It records
  every response by URL and SHA-256. When the user's environment names a
  proxy of its own, mitmproxy forwards to it.
- Wrappers of git, hg, svn and cvs, in `GIT_EXECUTABLE`, `HG_EXECUTABLE`,
  `Subversion_SVN_EXECUTABLE` and `CVS_EXECUTABLE`. Each logs every
  command that CMake's modules run with its tool and passes it on, with
  the user's own proxy settings. svn gets them as `--config-option`
  arguments, since it reads no proxy variables. The logs show which
  repository each checkout came from and which ref it asked for.
- A dependency provider, injected through
  `CMAKE_PROJECT_TOP_LEVEL_INCLUDES`, which records each
  `FetchContent_MakeAvailable()` dependency by name and where FetchContent
  put it.

The wrappers run each command through `lock/pin.py`, with the pins of the
existing lockfile: every checkout whose ref moves, at its locked
revision. A git pin points the remote-tracking branch, and a local branch
of the same name, at the locked commit after each clone and fetch, and
fetches the commit when a shallow clone lacks it. An hg, svn or cvs pin
adds the locked revision or date to the checkout and update commands.
`cmake-purifier update` leaves out the pins of what it updates.

A git checkout is hashed with `nix-prefetch-git`, the hash `fetchgit`
checks. A Mercurial, Subversion or CVS checkout is hashed by building the
nixpkgs fetcher of the sandbox build with a wrong hash and reading the
right one from the error. A CVS checkout without a tag or a date locks
the time of the lock run as its date. A `GIT_SUBMODULES` list locks the
repository with all of its submodules, and a build from the lockfile
empties the submodules the list leaves out. A redirect counts as the
file it leads to, and its target is left out, since such targets are
often signed URLs that expire. The install's manifest gives the installed
files, and CMake's File API gives the target each one belongs to.

The lock run configures with `CMAKE_BUILD_TYPE=Release` and
`CMAKE_INSTALL_LIBDIR=lib`, as nixpkgs' CMake setup hook does, so that the
recorded outputs are the outputs of the sandbox build. `--no-build` stops
the lock run after the configure, for a project whose build cannot run on
the machine that locks; the lockfile then records no outputs, and misses
anything the build itself downloads.

## A build from the lockfile

The sandbox build and the development loop after `cmake-purifier prefetch`
give every download its locked copy:

- FetchContent dependencies come from `FETCHCONTENT_SOURCE_DIR_<NAME>`,
  which the second dependency provider sets for each, with
  `FETCHCONTENT_FULLY_DISCONNECTED`. The sources are copies, because some
  projects write into their dependencies' source trees.
- Git, Mercurial, Subversion and CVS checkouts go to shims, which the
  initial cache names in `GIT_EXECUTABLE`, `HG_EXECUTABLE`,
  `Subversion_SVN_EXECUTABLE` and `CVS_EXECUTABLE`. They answer the
  checkout and update steps of `ExternalProject_Add()` and of FetchContent
  from the locked checkout of the repository and ref.
- Every other download goes to mitm-cache, as the HTTP and HTTPS proxy,
  which replays the locked files. In the sandbox its setup hook starts
  it, and `cmake-purifier replay` starts it around a command.

The provider checks every `FetchContent_MakeAvailable()` call, and the
shims check every checkout. Both kinds of build set
`FETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER`, as the lock run does, so a
dependency declared with `FIND_PACKAGE_ARGS` comes from its locked source
rather than from whatever `find_package()` finds on the machine that
runs the lock.

## Layout

- `cmake/`: the dependency providers of the lock run
  (`CMakePurifierLock.cmake`) and of builds from the lockfile
  (`CMakePurifierLocked.cmake`).
- `lock/`: the lock run's recorder addon for mitmproxy (`record.py`) and
  the script that writes the lockfile from the records (`assemble.py`).
- `lib-overlays/default/`: the public lock-reader closure. `lock.nix` reads the lockfile, checks its
  content hash and, with `definition-hash.nix`, its age, and documents
  its format. `pkgs/build-cmake-project/` owns `sources.nix`, which
  makes the tree a build from the lockfile reads, `write-cache.sh` writes
  its initial cache, `git-shim.sh` and `vcs-shim.sh` serve its
  checkouts, `prefetch-vcs.nix` fetches a Mercurial, Subversion or CVS checkout for
  the hash the lock run records, and `pkgs/build-cmake-project/default.nix` is
  `buildCMakeProject`, which `pkg-overlays/default` adds to the scope
  `pkgs.cmake-purifier`. `lib-overlays/default` publishes `lock.nix` as
  `lib.cmake-purifier.readLock`. Every fetch goes through the shared library
  `purifier`, a flake input, whose `fetchEntry` and `tree` take the
  download entries of the lockfile.
- `pkgs/cmake-purifier/`: the command.
- `configs/`, `lib-overlays/`, `pkg-overlays/`: the caisson flake layout.
- `tests/`: the checks, the fixtures and the scripts around them.

## Lockfile

`lib-overlays/default/lock.nix` documents the format. Its download entries are those
of the shared nix-purifiers library: a file is
`{ path, url, mirrors, hash }`, and a git checkout is
`{ path, git = { url, rev, submodules }, hash }`. A file's path is the
path mitm-cache replays it from. An archive is a file entry, which
`sources.nix` unpacks with CMake's own extraction rule: the archive's
single top-level directory is stripped when there is exactly one.
