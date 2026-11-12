# SPDX-License-Identifier: MIT
#
# Everything a build from a lockfile reads instead of the network. It is a
# package for callPackage, with the lockfile among its arguments.
# buildCMakeProject's `sources` is this, and `cmake-purifier configure`
# builds it on its own for an interactive build.
#
# Every artifact is a download entry of the shared library `purifier`,
# which fetches it (fetchEntry) and lays the file downloads out
# (tree). `tree` is one directory with these parts:
#
# - `deps/<name>`: the source tree of each FetchContent dependency, as
#   FetchContent would have populated it. `byName` maps each name to it.
# - `declared.tsv`: a line per FetchContent dependency with its name and
#   the download its declaration named in the lock run.
# - `git-checkouts.tsv`: a line per git checkout the build makes, with the
#   repository URL, the ref the build asked for, the commit and the store
#   path of the checkout, for git-shim.sh.
# - `hg-checkouts.tsv`, `svn-checkouts.tsv` and `cvs-checkouts.tsv`: a line
#   per Mercurial, Subversion and CVS checkout, with the repository, the
#   ref and the store path of the checkout, for vcs-shim.sh.
# - `http/`: every locked file at its artifact path, which is
#   `<scheme>/<host>/<path>` of its URL, the layout mitm-cache replays.
{
  lib,
  stdenv,
  runCommand,
  cmake,
  # The fetchers of the entries, and the packages that the steps after a
  # fetch build with, which fetchEntry of the shared library takes by name.
  fetchurl,
  fetchgit,
  fetchhg,
  fetchsvn,
  fetchcvs,
  unzip,
  zstd,
  python3,
  writeText,
  purifier,
  lockFile,
  # The project's source, for the check that the lockfile is not older
  # than the project; see lock.nix.
  projectSrc ? null,
  # Fetchers that replace the ones fetchEntry uses, by their names
  # (fetchurl, fetchgit, fetchhg, fetchsvn, fetchcvs), for credentials or
  # mirrors. Each takes the arguments of the nixpkgs fetcher of its name.
  fetchers ? { },
}:
let
  # The lock in memory, checked by the shared library, and the lockfile's
  # own fields.
  memory = purifier.checkLock (
    import ../../lib-overlays/default/lock.nix {
      inherit lockFile;
      src = projectSrc;
    }
  );
  lock = memory.cmake;
  # The entries this system needs, by path.
  entries = purifier.entriesFor stdenv.hostPlatform.system memory;
  entriesByPath = builtins.listToAttrs (
    map (entry: {
      name = entry.path;
      value = entry;
    }) entries
  );

  fetcherArgs = {
    inherit
      fetchurl
      fetchgit
      fetchhg
      fetchsvn
      fetchcvs
      runCommand
      unzip
      zstd
      python3
      writeText
      ;
  }
  // fetchers;

  # Each artifact fetched once, by its path.
  fetched = builtins.mapAttrs (_: purifier.fetchEntry fetcherArgs) entriesByPath;

  artifactOf =
    what: path:
    entriesByPath.${path}
      or (throw "cmake-purifier: ${what} names the artifact ${path}, which ${toString lockFile} does not lock");

  source =
    dep:
    let
      artifact = artifactOf "dependency ${dep.name}" dep.artifact;
      download = fetched.${dep.artifact};
    in
    if dep ? submodules then
      # A GIT_SUBMODULES list: the checkout holds every submodule, and the
      # source only the listed ones.
      runCommand "${lock.storeName dep.name}-source" { preferLocalBuild = true; } ''
        cp -R ${download} $out
        chmod -R u+w $out
        bash ${./prune-submodules.sh} $out ${lib.escapeShellArgs dep.submodules}
      ''
    else if !(artifact ? url) then
      download
    else if dep.extract then
      # FetchContent unpacks an archive with CMake's own rule, which strips
      # a single top-level directory only when there is exactly one.
      runCommand "${lock.storeName dep.name}-source"
        {
          nativeBuildInputs = [ cmake ];
          preferLocalBuild = true;
        }
        ''
          cmake -DARCHIVE=${download} -DOUT=$out -DWORK=$TMPDIR/extract -P ${./extract.cmake}
        ''
    else
      # DOWNLOAD_NO_EXTRACT: the source directory holds the downloaded file
      # under its own name.
      runCommand "${lock.storeName dep.name}-source" { preferLocalBuild = true; } ''
        mkdir $out
        ln -s ${download} $out/${lib.escapeShellArg (baseNameOf artifact.url)}
      '';

  byName = builtins.listToAttrs (
    map (dep: {
      inherit (dep) name;
      value = source dep;
    }) lock.dependencies
  );

  http = purifier.tree (
    fetcherArgs
    // {
      name = "cmake-purifier-http";
      entries = builtins.filter (artifact: artifact ? url) entries;
    }
  );

  checkoutTable =
    tool:
    lib.concatMapStrings (
      c:
      let
        artifact = artifactOf "the ${tool} checkout of ${c.repo} at ${c.ref}" c.artifact;
      in
      "${c.repo}\t${c.ref}\t${fetched.${artifact.path}}\n"
    ) (lock."${tool}Checkouts" or [ ]);
in
{
  inherit memory lock byName;
  # The manifests go to the builder as files, since a build can lock many
  # downloads.
  tree =
    runCommand "cmake-purifier-sources"
      {
        deps = lib.concatStrings (lib.mapAttrsToList (name: path: "${name}\t${path}\n") byName);
        declared = lib.concatMapStrings (dep: "${dep.name}\t${dep.declared or ""}\n") lock.dependencies;
        checkouts = lib.concatMapStrings (
          c:
          let
            artifact = artifactOf "the checkout of ${c.url} at ${c.ref}" c.artifact;
          in
          "${c.url}\t${c.ref}\t${artifact.git.rev}\t${fetched.${c.artifact}}\n"
        ) lock.gitCheckouts;
        hg = checkoutTable "hg";
        svn = checkoutTable "svn";
        cvs = checkoutTable "cvs";
        passAsFile = [
          "deps"
          "declared"
          "checkouts"
          "hg"
          "svn"
          "cvs"
        ];
        preferLocalBuild = true;
        allowSubstitutes = false;
      }
      ''
        mkdir -p $out/deps
        while IFS=$'\t' read -r name target; do
          ln -s "$target" "$out/deps/$name"
        done < "$depsPath"
        ln -s ${http} $out/http
        cp "$declaredPath" $out/declared.tsv
        cp "$checkoutsPath" $out/git-checkouts.tsv
        cp "$hgPath" $out/hg-checkouts.tsv
        cp "$svnPath" $out/svn-checkouts.tsv
        cp "$cvsPath" $out/cvs-checkouts.tsv
      '';
}
