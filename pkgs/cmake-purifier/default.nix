# SPDX-License-Identifier: MIT
#
# The `cmake-purifier` command.
#
#   cmake-purifier lock [--no-build] [-S <source dir>] [--lockfile <path>] [<cmake configure arguments>...]
#   cmake-purifier update [-S <source dir>] [--lockfile <path>] [<dependency or repository>...]
#   cmake-purifier prefetch [-S <source dir>] [--lockfile <path>]
#   cmake-purifier replay [-S <source dir>] [--lockfile <path>] -- <command>...
#   cmake-purifier publish [--lockfile <path>] [--repo <owner>/<name>] <tag> <installable>
#
# The lockfile is <source dir>/cmake-purifier.lock.json, unless
# --lockfile or, after it, the environment variable CMAKE_PURIFIER_LOCKFILE
# names another. The directory .cmake-purifier beside the lockfile holds
# what `prefetch` writes.
#
# `lock` configures and builds the project once in a scratch directory,
# with the network and an empty FetchContent download directory. Three
# recorders see its downloads: mitmproxy as the HTTP and HTTPS proxy of
# CMake and everything it runs (lock/record.py), a git wrapper in
# GIT_EXECUTABLE that logs every git command, and the dependency provider
# cmake/CMakePurifierLock.cmake, which names the FetchContent dependency
# each download belongs to. lock/assemble.py turns the three records into
# the lockfile (see nix/lib/lock.nix for the format). The configure arguments go into the lockfile too, since they
# decide which downloads the build makes; every build of the lockfile
# passes them first. After the build, `lock` installs the project into a
# scratch prefix and records what it installed, so that Nix knows the
# outputs of the build without building it. `--no-build` stops after the
# configure, and then the lockfile misses what the build itself downloads,
# and records no outputs.
#
# `lock` keeps what the lockfile already resolved: a checkout whose ref
# moves, such as a git branch, an svn checkout at HEAD or a CVS checkout
# without a tag, stays at its locked revision (lock/pin.py). `update`
# relocks with the configure arguments of the lockfile and moves those
# checkouts to where their refs point now: every one, or those of the
# named FetchContent dependencies and repositories.
#
# `prefetch` builds every locked download through Nix and keeps it with a
# garbage-collector root, .cmake-purifier/sources-root. It
# copies the FetchContent dependencies to .cmake-purifier/sources and
# writes .cmake-purifier/initial-cache.txt, the initial cache of the
# development loop: `cmake -C .cmake-purifier/initial-cache.txt -B <build
# dir>` points FetchContent at the copies and git, hg, svn and cvs at the
# locked checkouts, and sets the configure arguments of the lock run and
# CMAKE_EXPORT_COMPILE_COMMANDS, for the editor. After a prefetch, the
# configure, the build and ctest need no network.
#
# `replay` runs a command with mitm-cache as its HTTP and HTTPS proxy,
# replaying the locked files from the prefetch. A project needs it for the
# downloads outside FetchContent and the version-control tools, which
# CMake makes with its own HTTP client: file(DOWNLOAD) and
# ExternalProject_Add() with a URL.
#
# `publish` builds <installable>, the `release` of buildCMakeProject, and
# uploads each file in it to the GitHub release <tag> with `gh release
# upload`.
#
# The commands run the `nix-build` and `nix build` of the user's own Nix
# installation, and `lock` runs its own nix-prefetch-git.
{
  pkgs,
  writeShellApplication,
  runtimeShell,
  cmake,
  git,
  mercurial,
  subversion,
  cvs,
  jq,
  mitmproxy,
  mitm-cache,
  nix-prefetch-git,
  openssl,
  python3,
  python3Packages,
  coreutils,
  gh,
  # The source of the shared library of the nix-purifiers, which the
  # package overlay passes.
  purifier ? throw "cmake-purifier: the command needs the source of the shared purifier library; take it from this flake's overlay",
}:
writeShellApplication {
  name = "cmake-purifier";
  runtimeInputs = [
    cmake
    jq
    mitmproxy
    mitm-cache
    openssl
    python3Packages.ephemeral-port-reserve
    coreutils
  ];
  meta = {
    description = "Lock the downloads of a CMake build, and prefetch them for an offline build";
    mainProgram = "cmake-purifier";
  };
  text = ''
    lockVersion=${toString (import ../../nix/lib/lock-version.nix)}
    provider=${../../cmake}/CMakePurifierLock.cmake
    lockedProvider=${../../cmake}/CMakePurifierLocked.cmake
    nixlib=${../../nix/lib}
    purifierlib=${purifier}
    lockdir=${../../lock}
    nixpkgs=${pkgs.path}
    realGit=${git}/bin/git
    realHg=${mercurial}/bin/hg
    realSvn=${subversion}/bin/svn
    realCvs=${cvs}/bin/cvs
    python=${python3}/bin/python3
    prefetchGit=${nix-prefetch-git}/bin/nix-prefetch-git

    usage() {
      cat >&2 <<'EOF'
    usage: cmake-purifier lock [--no-build] [-S <source dir>] [--lockfile <path>] [<cmake configure arguments>...]
           cmake-purifier update [-S <source dir>] [--lockfile <path>] [<dependency or repository>...]
           cmake-purifier prefetch [-S <source dir>] [--lockfile <path>]
           cmake-purifier replay [-S <source dir>] [--lockfile <path>] -- <command>...
           cmake-purifier publish [--lockfile <path>] [--repo <owner>/<name>] <tag> <installable>
    EOF
      exit 2
    }

    die() {
      echo "cmake-purifier: $*" >&2
      exit 1
    }

    [ $# -ge 1 ] || usage
    command=$1
    shift

    # -S, --lockfile, --repo and --no-build are read here, -S in the separate
    # and the attached form. For lock, every other argument goes to cmake,
    # and for replay, everything after `--` is the command.
    source=.
    lockfile=
    repo=
    noBuild=
    updateNames=()
    updateAll=
    args=()
    while [ $# -gt 0 ]; do
      case "$1" in
        -S) [ $# -ge 2 ] || usage; source=$2; shift 2 ;;
        -S*) source=''${1#-S}; shift ;;
        --lockfile) [ $# -ge 2 ] || usage; lockfile=$2; shift 2 ;;
        --lockfile=*) lockfile=''${1#--lockfile=}; shift ;;
        --repo) [ $# -ge 2 ] || usage; repo=$2; shift 2 ;;
        --no-build) noBuild=1; shift ;;
        --) [ "$command" = replay ] || usage; shift; args+=("$@"); break ;;
        *) args+=("$1"); shift ;;
      esac
    done
    source=$(realpath "$source")
    lockfile=$(realpath -m "''${lockfile:-''${CMAKE_PURIFIER_LOCKFILE:-$source/cmake-purifier.lock.json}}")
    state=$(dirname "$lockfile")/.cmake-purifier

    # Waits until something listens on 127.0.0.1:<port>.
    await_port() {
      for _ in $(seq 100); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then
          return 0
        fi
        sleep 0.1
      done
      die "the proxy on port $1 did not start"
    }

    # The environment that sends HTTP and HTTPS through the proxy on
    # 127.0.0.1:<port> and trusts the certificate authority <ca>.
    proxy_env() {
      export http_proxy="http://127.0.0.1:$1" https_proxy="http://127.0.0.1:$1"
      export HTTP_PROXY="$http_proxy" HTTPS_PROXY="$https_proxy"
      unset ALL_PROXY all_proxy
      # Requests to the machine itself, such as a test's own server, are
      # no downloads, and go around the proxy. Every other host goes
      # through it, whatever the user's NO_PROXY names.
      export no_proxy="localhost,127.0.0.1,::1" NO_PROXY="localhost,127.0.0.1,::1"
      export SSL_CERT_FILE="$2" NIX_SSL_CERT_FILE="$2" CURL_CA_BUNDLE="$2"
    }

    lock() {
      [ -f "$source/CMakeLists.txt" ] || die "$source has no CMakeLists.txt"
      started=$SECONDS
      # The physical path, as the tools record their working directories:
      # on macOS the temporary directory is under the symlinks /var or /tmp.
      work=$(realpath "$(mktemp -d)")
      trap 'kill "''${recorder:-}" 2>/dev/null || true; chmod -R u+w "$work" 2>/dev/null || true; rm -rf "$work"' EXIT

      # mitmproxy forwards to the user's own proxy when one is set.
      mode=regular
      upstreamArgs=()
      svnArgs=()
      upstream=''${https_proxy:-''${HTTPS_PROXY:-}}
      if [ -n "$upstream" ]; then
        hostport=''${upstream#*://}
        hostport=''${hostport%/}
        if [ "''${hostport#*@}" != "$hostport" ]; then
          creds=''${hostport%@*}
          upstreamArgs=(--set "upstream_auth=$creds")
          hostport=''${hostport#*@}
          svnArgs+=(--config-option="servers:global:http-proxy-username=''${creds%%:*}")
          svnArgs+=(--config-option="servers:global:http-proxy-password=''${creds#*:}")
        fi
        mode="upstream:http://$hostport"
        # svn reads no proxy variables, only its own configuration.
        svnArgs+=(--config-option="servers:global:http-proxy-host=''${hostport%:*}")
        svnArgs+=(--config-option="servers:global:http-proxy-port=''${hostport##*:}")
      fi

      # Writes $work/<tool>, a wrapper that logs each command with its
      # working directory to $work/<tool>.jsonl and runs <real> with the
      # user's own network environment and any further arguments given,
      # through lock/pin.py, which keeps the pinned checkouts at their
      # locked revisions.
      make_logger() {
        local tool=$1 real=$2
        shift 2
        {
          echo "#!${runtimeShell}"
          for var in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy NO_PROXY no_proxy SSL_CERT_FILE NIX_SSL_CERT_FILE CURL_CA_BUNDLE; do
            if [ -n "''${!var+set}" ]; then
              printf 'export %s=%q\n' "$var" "''${!var}"
            else
              printf 'unset %s\n' "$var"
            fi
          done
          # The wrapper expands $PWD and $@ itself, and jq the filter.
          # shellcheck disable=SC2016
          printf '%q -cn --arg cwd "$PWD" %q --args -- "$@" >> %q\n' \
            "$(command -v jq)" '{cwd: $cwd, args: $ARGS.positional}' "$work/$tool.jsonl"
          printf 'exec %q -I %q %q %q %q %q' "$python" "$lockdir/pin.py" "$tool" "$work/pins.json" "$real" "$#"
          for extra in "$@"; do
            printf ' %q' "$extra"
          done
          # shellcheck disable=SC2016
          printf ' -- "$@"\n'
        } > "$work/$tool"
        chmod +x "$work/$tool"
      }
      # The pins: every locked checkout whose ref moves, from the lockfile
      # as it is, without the ones `update` updates.
      echo '[]' > "$work/pins.json"
      if jq -e --argjson version "$lockVersion" '.version == $version' "$lockfile" > /dev/null 2>&1; then
        jq --argjson updated "$(jq -n '$ARGS.positional' --args -- ''${updateNames[@]+"''${updateNames[@]}"})" \
          --argjson all "''${updateAll:-false}" '
          (.artifacts | map({ key: .path, value: . }) | from_entries) as $by
          | ([.dependencies[] | select(.name as $n | $updated | index($n)) | .artifact]) as $named
          | [
              (.gitCheckouts[] | { tool: "git", repo: .url, ref, rev: $by[.artifact].git.rev, artifact }),
              ((.hgCheckouts // [])[] | { tool: "hg", repo, ref, rev: $by[.artifact].hg.rev, artifact }),
              ((.svnCheckouts // [])[] | { tool: "svn", repo, ref, rev: ($by[.artifact].svn.rev | tostring), artifact }),
              ((.cvsCheckouts // [])[] | select(.ref == "") | { tool: "cvs", repo, ref, rev: $by[.artifact].cvs.date, artifact })
            ]
          | if $all then [] else map(select((.artifact as $a | $named | index($a)) or (.repo as $r | $updated | index($r)) | not)) end
          ' "$lockfile" > "$work/pins.json"
      fi
      make_logger git "$realGit"
      make_logger hg "$realHg"
      make_logger svn "$realSvn" ''${svnArgs[@]+"''${svnArgs[@]}"}
      make_logger cvs "$realCvs"
      port=$(ephemeral-port-reserve 127.0.0.1)
      PURIFIER_RECORD="$work/http.jsonl" mitmdump -q --listen-host 127.0.0.1 --listen-port "$port" \
        --mode "$mode" ''${upstreamArgs[@]+"''${upstreamArgs[@]}"} --set confdir="$work/mitmproxy" \
        -s "$lockdir/record.py" &
      recorder=$!
      await_port "$port"

      echo "cmake-purifier: configuring $source to record its downloads" >&2
      # The File API's code model names the targets and where they install.
      mkdir -p "$work/build/.cmake/api/v1/query"
      touch "$work/build/.cmake/api/v1/query/codemodel-v2"
      (
        proxy_env "$port" "$work/mitmproxy/mitmproxy-ca-cert.pem"
        unset CPM_SOURCE_CACHE
        # CMAKE_INSTALL_LIBDIR and CMAKE_BUILD_TYPE are what nixpkgs' CMake
        # setup hook sets, so that the recorded outputs match the outputs
        # of the sandbox build. The build type decides the names of some
        # installed files, such as <package>-targets-release.cmake. A
        # -DCMAKE_BUILD_TYPE among the user's arguments comes later and
        # wins, and the lockfile records it for the sandbox build.
        cmake -S "$source" -B "$work/build" \
          -DCMAKE_INSTALL_LIBDIR=lib \
          -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_PROJECT_TOP_LEVEL_INCLUDES="$provider" \
          -DCMAKE_PURIFIER_OBSERVED="$work/observed.json" \
          -DFETCHCONTENT_BASE_DIR="$work/deps" \
          -DFETCHCONTENT_TRY_FIND_PACKAGE_MODE=NEVER \
          -DFETCHCONTENT_FULLY_DISCONNECTED=OFF \
          -DGIT_EXECUTABLE="$work/git" \
          -DHG_EXECUTABLE="$work/hg" \
          -DSubversion_SVN_EXECUTABLE="$work/svn" \
          -DCVS_EXECUTABLE="$work/cvs" \
          ''${args[@]+"''${args[@]}"} >&2
        if [ -z "$noBuild" ]; then
          echo "cmake-purifier: building $source to record what the build downloads" >&2
          # A bare --parallel lets make start any number of jobs.
          cmake --build "$work/build" --parallel "''${CMAKE_BUILD_PARALLEL_LEVEL:-$(nproc)}" >&2
          echo "cmake-purifier: installing $source to record its outputs" >&2
          cmake --install "$work/build" --prefix "$work/prefix" >&2
        fi
      )
      kill "$recorder"
      wait "$recorder" 2>/dev/null || true
      recorder=
      [ -f "$work/observed.json" ] || die "the configure run wrote no record of its dependencies"

      jq -n '$ARGS.positional' --args -- ''${args[@]+"''${args[@]}"} > "$work/flags.json"
      "$python" -I "$lockdir/assemble.py" "$work" "$lockVersion" "$lockfile" "$nixpkgs" \
        "$nixlib" "$purifierlib" "$realGit" "$realHg" "$realSvn" "$prefetchGit" \
        "$(PATH="${git}/bin:$PATH" bash "$nixlib/definition-hash.sh" "$source")" "$work/pins.json"
      echo "cmake-purifier: locked in $((SECONDS - started)) seconds" >&2
    }

    # Stops unless the lockfile is valid JSON in this command's format and
    # the project's build definition is the one it was written for. The
    # Nix library checks the content hash when it reads the lockfile.
    check_lockfile() {
      [ -f "$lockfile" ] || die "$lockfile does not exist; run cmake-purifier lock first"
      jq -e 'type == "object"' "$lockfile" > /dev/null 2>&1 ||
        die "$lockfile is not valid JSON; restore it from version control, or run cmake-purifier lock to write it again"
      format=$(jq .version "$lockfile")
      [ "$format" = "$lockVersion" ] || die "$lockfile has lock format version $format; this cmake-purifier reads version $lockVersion. Run cmake-purifier lock again."
      locked=$(jq -r '.definitionHash // ""' "$lockfile")
      current=$(PATH="${git}/bin:$PATH" bash "$nixlib/definition-hash.sh" "$source")
      [ "$locked" = "$current" ] ||
        die "$lockfile is older than the project: a CMakeLists.txt or *.cmake file changed since it was written. Run cmake-purifier lock to lock the project again."
    }

    prefetch() {
      [ -f "$source/CMakeLists.txt" ] || die "$source has no CMakeLists.txt"
      check_lockfile
      mkdir -p "$state"
      # Git ignores everything in the directory, this file included.
      echo '*' > "$state/.gitignore"
      tree=$(nix-build --expr \
        "{ lockFile }: let pkgs = import $nixpkgs { }; in (pkgs.callPackage $nixlib/sources.nix { inherit lockFile; purifier = import $purifierlib { inherit (pkgs) lib; }; }).tree" \
        --arg lockFile "$lockfile" --out-link "$state/sources-root")
      cache=$state/initial-cache.txt
      bash "$nixlib/write-cache.sh" "$tree" "$state/sources" "$cache" \
        "$lockedProvider" "$nixlib" "$realGit" "$realHg" "$realSvn" "$realCvs"
      # The configure arguments of the lock run, as cache entries.
      {
        echo 'set(CMAKE_EXPORT_COMPILE_COMMANDS ON CACHE BOOL "" FORCE)'
        jq -r '.cmakeFlags[]' "$lockfile" | while IFS= read -r flag; do
          case "$flag" in
            -D*=*)
              definition=''${flag#-D}
              name=''${definition%%=*}
              value=''${definition#*=}
              type=STRING
              if [ "''${name#*:}" != "$name" ]; then
                type=''${name#*:}
                name=''${name%%:*}
              fi
              printf 'set(%s [==[%s]==] CACHE %s "" FORCE)\n' "$name" "$value" "$type"
              ;;
            *) echo "cmake-purifier: the lock run had the configure argument $flag; pass it to cmake yourself" >&2 ;;
          esac
        done
      } >> "$cache"
      echo "cmake-purifier: prefetched the downloads of $lockfile into $state" >&2
      echo "cmake-purifier: configure with: cmake -S $source -B <build dir> -C $cache" >&2
      if jq -e '[.artifacts[] | select(.url != null) | .path] - [.dependencies[].artifact] | length > 0' "$lockfile" > /dev/null; then
        echo "cmake-purifier: the build downloads files outside FetchContent; run the configure and the build under cmake-purifier replay --" >&2
      fi
    }

    # Runs a command with mitm-cache replaying the prefetched files as its
    # proxy.
    replay() {
      [ ''${#args[@]} -gt 0 ] || usage
      [ -e "$state/sources-root" ] || die "$source has no prefetched downloads; run cmake-purifier prefetch first"
      check_lockfile
      tree=$(readlink -f "$state/sources-root")
      ca=$state/ca
      mkdir -p "$ca"
      [ -f "$ca/ca.cer" ] || {
        openssl genrsa -out "$ca/ca.key" 2048 2>/dev/null
        openssl req -x509 -new -nodes -key "$ca/ca.key" -sha256 -days 3650 -out "$ca/ca.cer" -subj "/CN=cmake-purifier" 2>/dev/null
      }
      port=$(ephemeral-port-reserve 127.0.0.1)
      mitm-cache -l "127.0.0.1:$port" -k "$ca/ca.key" -c "$ca/ca.cer" replay "$tree/http" >/dev/null 2>&1 &
      replayer=$!
      trap 'kill "$replayer" 2>/dev/null || true' EXIT
      await_port "$port"
      status=0
      ( proxy_env "$port" "$ca/ca.cer"; "''${args[@]}" ) || status=$?
      exit "$status"
    }

    publish() {
      [ ''${#args[@]} -eq 2 ] || usage
      tag=''${args[0]}
      release=$(nix build --no-link --print-out-paths "''${args[1]}")
      files=()
      for file in "$release"/*; do
        [ -f "$file" ] && files+=("$file")
      done
      [ ''${#files[@]} -gt 0 ] || die "''${args[1]} built $release, which holds no files to upload"
      repoArgs=()
      [ -z "$repo" ] || repoArgs=(--repo "$repo")
      # The user's own gh, which holds their login, or nixpkgs' one.
      ghCommand=$(command -v gh || echo ${gh}/bin/gh)
      "$ghCommand" release upload "$tag" "''${files[@]}" --clobber ''${repoArgs[@]+"''${repoArgs[@]}"}
      echo "cmake-purifier: uploaded ''${#files[@]} files to the release $tag" >&2
    }

    # Relocks with the configure arguments of the lockfile, moving the
    # checkouts of the named dependencies or repositories, or of every one.
    update() {
      [ -f "$lockfile" ] || die "$lockfile does not exist; run cmake-purifier lock first"
      jq -e --argjson version "$lockVersion" '.version == $version' "$lockfile" > /dev/null 2>&1 ||
        die "$lockfile is not a cmake-purifier lockfile of version $lockVersion; run cmake-purifier lock to write it again"
      updateNames=(''${args[@]+"''${args[@]}"})
      if [ ''${#updateNames[@]} -eq 0 ]; then
        updateAll=true
      fi
      for name in ''${updateNames[@]+"''${updateNames[@]}"}; do
        jq -e --arg name "$name" '
          [.dependencies[].name, (.gitCheckouts[].url), ((.hgCheckouts // [])[].repo),
           ((.svnCheckouts // [])[].repo), ((.cvsCheckouts // [])[].repo)] | index($name)' "$lockfile" > /dev/null ||
          die "$lockfile has no dependency or repository named $name"
      done
      mapfile -t args < <(jq -r '.cmakeFlags[]' "$lockfile")
      lock
    }

    case "$command" in
      lock) lock ;;
      update) update ;;
      prefetch) prefetch ;;
      replay) replay ;;
      publish) publish ;;
      *) usage ;;
    esac
  '';
}
