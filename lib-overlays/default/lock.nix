# SPDX-License-Identifier: MIT
#
# readLock: reads a cmake-purifier lockfile (written by `cmake-purifier
# lock`) into the lock in memory of the purifier contract:
#
#   { purifier = "cmake-purifier"; entries; outputs; problems; cmake; }
#
# `entries` is the lockfile's `artifacts`, needed on every system.
# `outputs` holds the lockfile's `outputs` under the name of the top-level
# project(), and is empty for a lockfile without outputs. `problems` holds
# a message for a lockfile that is incomplete, of another format version,
# edited, or older than `src`, each naming the command that fixes it; the
# builder hands the lock to the shared library's checkLock, which fails
# evaluation with them. A file that is not valid JSON fails evaluation
# when it is read, with the hint to restore or relock it. `cmake` is the
# lockfile itself, with the helpers sources.nix uses.
#
# The file holds these fields.
#
# `artifacts` is every download of the build. An artifact is either a
# file, `{ path, url, mirrors, hash }` with the SRI hash of the file and a
# list of further URLs that serve the same bytes, or a git
# checkout, `{ path, git = { url, rev, submodules, leaveDotGit,
# commitObject }, hash }` with the SRI NAR hash of the checkout as fetchgit
# makes it, where cmake-purifier writes `leaveDotGit = false` and
# `commitObject = null`, since the git shim needs no `.git`, or a checkout from another
# version-control system: `hg = { url, rev, subrepos }`,
# `svn = { url, rev, ignoreExternals, ignoreKeywords }`, or
# `cvs = { cvsRoot, module, tag, date }` with one of `tag` and `date` null,
# each with the hash of the nixpkgs fetcher's output. These are the
# download entries of the shared nix-purifiers library. A file's `path` is
# `<scheme>/<host>/<path>` of its URL, where mitm-cache replays it; a
# checkout's `path` starts with its tool and ends with its revision.
#
# `dependencies` is every FetchContent_MakeAvailable() dependency, by its
# FetchContent `name`. Its `artifact` is the path of its download. A
# dependency on a file also says whether FetchContent `extract`s it.
#
# `gitCheckouts` is every git checkout the build makes, by repository
# `url` and the `ref` the build checks out, with the path of its
# `artifact`. `hgCheckouts`, `svnCheckouts` and `cvsCheckouts` are the
# checkouts of the other tools, by `repo` and `ref` as vcs-shim.sh reads
# them, with the path of their `artifact`.
#
# `outputs` is what the install writes: `files`, every installed file by
# its path relative to the install prefix, and `targets`, each installed
# target by name with its CMake `type` and the installed `files` of its
# artifacts. It is null when the lock run did not build.
#
# `definitionHash` is the hash of the project's build definition
# (definition-hash.nix), and `contentHash` the SHA-256 of the lockfile
# itself without its contentHash, as builtins.toJSON writes it. A
# lockfile whose content does not hash to its contentHash was edited, and
# fails. With `src`, the project's source as a path, a lockfile whose
# definitionHash is not the hash of `src` is older than the project, and
# fails too.
{
  src ? null,
  lockFile ? src + "/cmake-purifier.lock.json",
}:
let
  hint = "Restore ${toString lockFile} from version control, or run `cmake-purifier lock` to write it again.";

  file = builtins.addErrorContext "while reading the cmake-purifier lockfile ${toString lockFile}. ${hint}" (
    builtins.fromJSON (builtins.readFile lockFile)
  );

  required = [
    "version"
    "project"
    "definitionHash"
    "cmakeFlags"
    "artifacts"
    "dependencies"
    "gitCheckouts"
    "outputs"
    "contentHash"
  ];
  missing = builtins.filter (key: !(builtins.isAttrs file && file ? ${key})) required;

  supportedVersion = import ./lock-version.nix;

  contentHash =
    "sha256:" + builtins.hashString "sha256" (builtins.toJSON (removeAttrs file [ "contentHash" ]));

  definitionHash = import ./definition-hash.nix;

  # The first problem only: a lockfile without its keys has no version to
  # compare, and one of another version has no content hash to check.
  problems =
    if missing != [ ] then
      [
        "cmake-purifier: ${toString lockFile} is not a cmake-purifier lockfile: it has no ${builtins.concatStringsSep ", " missing}. ${hint}"
      ]
    else if file.version != supportedVersion then
      [
        "cmake-purifier: ${toString lockFile} has lock format version ${toString file.version}; this library reads version ${toString supportedVersion}. Run `cmake-purifier lock` with the cmake-purifier version that provides this library."
      ]
    else if file.contentHash != contentHash then
      [
        "cmake-purifier: ${toString lockFile} was edited: its content no longer matches its contentHash. ${hint}"
      ]
    else if builtins.isPath src && file.definitionHash != definitionHash src then
      [
        "cmake-purifier: ${toString lockFile} is older than the project: a CMakeLists.txt or *.cmake file changed since it was written. Run `cmake-purifier lock` to lock the project again."
      ]
    else
      [ ];
  usable = problems == [ ];

  # A store path name from a file name. Store path names allow
  # [A-Za-z0-9+._?=-], must not start with a dot, and are at most 211
  # characters; every other character becomes "_".
  storeName =
    fileName:
    let
      # builtins.split alternates the text between matches with a list per
      # match.
      replaced = builtins.concatStringsSep "" (
        map (part: if builtins.isList part then "_" else part) (
          builtins.split "[^A-Za-z0-9+._?=-]" fileName
        )
      );
      undotted = builtins.head (builtins.match "\\.*(.*)" replaced);
      nonEmpty = if undotted == "" then "file" else undotted;
    in
    builtins.substring 0 200 nonEmpty;
in
if builtins.isAttrs file && (file.version or null) == 4 then
  import ./legacy-lock.nix { inherit src lockFile; }
else
  {
    purifier = "cmake-purifier";
    entries = if usable then file.artifacts else [ ];
    outputs = if usable && file.outputs != null then { ${file.project.name} = file.outputs; } else { };
    inherit problems;

    cmake = file // {
      inherit storeName;

      # The fetch name of an artifact: the last component of its path, made a
      # valid store name.
      artifactName = artifact: storeName (baseNameOf artifact.path);

      artifactsByPath = builtins.listToAttrs (
        map (a: {
          name = a.path;
          value = a;
        }) file.artifacts
      );
    };
  }
