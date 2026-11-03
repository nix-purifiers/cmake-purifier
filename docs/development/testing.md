# Testing

The tests come in four layers. The `conformance-*` names are the checks
of the purifier contract; the ones that need Nix or the network outside
the sandbox are CI jobs of the same name.

1. **Flake checks** (`tests/default.nix`) run in the sandbox under
   `nix flake check`:
   - `basic` builds `tests/fixtures/basic` with `buildCMakeProject`, and
     `basic-tests` runs its ctest suite. The fixture has a FetchContent
     dependency of each kind: an archive (fmt), a git checkout declared in
     a subdirectory (argparse, in `lib/`), and a single header that
     FetchContent does not extract (doctest).
   - `extras` builds `tests/fixtures/extras`, whose downloads happen
     outside `FetchContent_MakeAvailable()`: `file(DOWNLOAD)` at configure
     time (CPM.cmake) and at build time (fmt's license, in a `cmake -P`
     script), CPM.cmake packages through `FetchContent_MakeAvailable()`
     (argparse) and `FetchContent_Populate()` (cxxopts, `DOWNLOAD_ONLY`),
     and `ExternalProject_Add()` with an archive that it builds (zlib) and
     with a git checkout (expected-lite).
   - `vcs` builds `tests/fixtures/vcs`, with a FetchContent dependency
     from Subversion, an `ExternalProject_Add()` checkout from Mercurial,
     and a git repository with two submodules, checked out by FetchContent
     and by `ExternalProject_Add()` with a `GIT_SUBMODULES` list each.
     `vcs-repos` builds its repositories (`tests/vcs-repos.nix`), so no
     check needs a server.
   - `cvs` builds `tests/fixtures/cvs`, an `ExternalProject_Add()`
     checkout of a CVS tag, and `cvs-runs` runs it. nixpkgs' cvs aborts on
     aarch64-linux, so there `cvs` is a check that prints that it skips the
     fixture.
   - `basic-runs`, `extras-runs` and `vcs-runs` run the installed
     programs. `basic-name` checks that the package name and version come
     from the fixture's `project()`, and `basic-outputs` and
     `extras-outputs` check the `targets` and `installed` the lockfiles
     name, at evaluation time.
   - `basic-release` checks the tarball of `release`, and `basic-fetches`
     checks that `fetches` is the lockfile's artifacts.
   - `definition-hash` checks that the shell and the Nix definition hash
     agree on every fixture and match its lockfile.
   - `conformance-stale` checks that a lockfile older than the project
     fails at evaluation, for a `src` that is a path, and before the
     configure, for a `src` that is a derivation.
   - `conformance-tampered` checks that a lockfile with an edited hash
     fails at evaluation, against its contentHash.
   - `conformance-missing` checks that a lockfile without a dependency the
     build declares stops the configure with the hint to relock.
   - `conformance-malformed` checks that invalid JSON and a JSON object
     without the required keys fail at evaluation, naming the command.
   - `conformance-external` builds the basic fixture from a `src` without
     a lockfile and the lockfile kept outside it.
   - `lock-urls` and `lock-records` check the URL rules and the reading of
     the records of the lock run (`lock/urls.py`, `lock/records.py`).
   - `real-world-cpr` builds libcpr/cpr 1.15.1 from its pinned source and
     the lockfile in `tests/real-world/cpr`, and runs its test suites.
     `real-world-cpr-src` and `real-world-cpr-shell` are the source and
     the development shell that the relock locks it with. Its lockfile,
     locked on Linux, names Linux's shared libraries, so elsewhere
     `real-world-cpr` is a check that prints that it skips the project.
   - `nix-library` runs `tests/nix-library.nix`, which applies the library
     to a hand-written lockfile with fetchers that download nothing.
   - `cmake-purifier` builds the command, which runs shellcheck on it.
   - `treefmt` checks the formatting of the Nix files.

   The evaluation checks run `nix-instantiate` on a dummy store inside the
   sandbox, on copies of `nix/lib` and the lockfile, so that they can
   match the error message.
2. **conformance-offline** (`tests/offline.sh`) prefetches every fixture
   with the network, then runs its development loop of plain `cmake`,
   `cmake --build`, ctest and clangd in a network namespace without a
   network. It runs after the flake checks, which fetch the vcs fixture's
   checkouts. Without user namespaces, it runs the loop on the host's
   network; CI requires the namespace.
3. **The command tests** (`tests/negative.sh`) run `cmake-purifier
   prefetch` on copies of the basic fixture with an invalid, an edited, a
   stale and an incomplete lockfile, each of which must stop with its
   message. They prefetch a project from a lockfile outside it, and run
   `publish` with a stand-in for gh.
4. **conformance-relock** (`tests/relock-fixtures.sh`) runs the lock run
   on the fixtures and on cpr, with the network. CI fails when a lockfile changes, so
   the lock run must reproduce the committed lockfiles byte for byte.
   **conformance-rebuild** is the CI job that builds fixtures again with
   `nix build --rebuild`. **conformance-update** (`tests/update.sh`)
   locks a project that follows two local git branches, one of them
   shallow, moves both branches, and checks that `lock` keeps the locked
   commits, `update <name>` moves one, and `update` moves both.

CI (`.github/workflows/check.yml`) runs every layer on x86_64-linux and
on GitHub's aarch64-linux runner.
