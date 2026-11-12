# SPDX-License-Identifier: MIT
#
# The git of a build from the lockfile. The initial cache names a wrapper
# around this script in GIT_EXECUTABLE, so every clone that CMake's own
# modules make goes through it: ExternalProject_Add(), FetchContent
# outside FetchContent_MakeAvailable(), and wrappers on top of them such as
# CPM.cmake.
#
# The wrapper sets three variables. CMAKE_PURIFIER_GIT_TABLE names the
# table of locked checkouts, a line per checkout with the repository URL,
# the ref the build asked for, the commit and the store path of the
# checkout, separated by tabs. CMAKE_PURIFIER_REAL_GIT is the git that
# runs every command this script does not answer itself, and
# CMAKE_PURIFIER_PRUNE is prune-submodules.sh.
#
# ExternalProject clones in three steps: `git clone <options> <url> <dir>`,
# then `git checkout <ref>` in <dir>, then `git submodule update` there. Its
# update step asks `git rev-parse` for the commits of HEAD and the ref, and
# finds nothing to do when they agree. The script answers those commands
# from the table: the clone makes <dir> and marks it with the URL, the
# checkout copies the locked checkout of that URL and ref into it, and
# every later command in <dir> sees the locked commit. The fetchgit
# checkout already holds the submodules the lock run initialized.
#
# The script reads the table with bash alone, and needs only coreutils
# besides, since a configure outside the sandbox has whatever PATH the
# user has.
set -eu
shopt -s dotglob nullglob

table=$CMAKE_PURIFIER_GIT_TABLE
real=$CMAKE_PURIFIER_REAL_GIT
marker=.cmake-purifier-checkout

die() {
  echo "cmake-purifier: $*" >&2
  exit 128
}

dir=$PWD
args=("$@")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  case "${args[$i]}" in
    -C)
      dir=$(cd "$dir" && cd "${args[$((i + 1))]}" && pwd)
      i=$((i + 2))
      ;;
    -c) i=$((i + 2)) ;;
    --git-dir=* | --work-tree=* | --no-pager | --literal-pathspecs | --no-replace-objects) i=$((i + 1)) ;;
    *) break ;;
  esac
done
sub=${args[$i]:-}
rest=("${args[@]:$((i + 1))}")

# Sets found_rev and found_path from the table line of URL $1 and ref $2,
# where the ref may also be the commit. With no $2, any line of the URL
# matches.
lookup() {
  found_rev=
  found_path=
  while IFS=$'\t' read -r t_url t_ref t_rev t_path; do
    if [ "$t_url" = "$1" ] && { [ $# -lt 2 ] || [ "$t_ref" = "$2" ] || [ "$t_rev" = "$2" ]; }; then
      found_rev=$t_rev
      found_path=$t_path
      return 0
    fi
  done < "$table"
  return 1
}

case "$sub" in
  clone)
    [ "${#rest[@]}" -ge 2 ] || exec "$real" "$@"
    url=${rest[$((${#rest[@]} - 2))]}
    dest=${rest[$((${#rest[@]} - 1))]}
    case "$dest" in /*) ;; *) dest=$dir/$dest ;; esac
    lookup "$url" ||
      die "the build clones $url, which the lockfile does not hold. Run \`cmake-purifier lock\` to lock it."
    mkdir -p "$dest"
    printf '%s\n' "$url" > "$dest/$marker"
    exit 0
    ;;
esac

if [ ! -f "$dir/$marker" ]; then
  exec "$real" "$@"
fi

{
  IFS= read -r url
  IFS= read -r rev || rev=
} < "$dir/$marker"
case "$sub" in
  checkout)
    ref=${rest[0]:-}
    lookup "$url" "$ref" ||
      die "the build checks out $ref of $url, which the lockfile does not hold. Run \`cmake-purifier lock\` to lock it."
    rev=$found_rev
    for entry in "$dir"/*; do
      [ "${entry##*/}" = "$marker" ] || rm -rf "$entry"
    done
    cp -R "$found_path/." "$dir/"
    chmod -R u+w "$dir"
    printf '%s\n%s\n%s\n' "$url" "$rev" "$ref" > "$dir/$marker"
    ;;
  rev-parse)
    [ -n "$rev" ] || die "git rev-parse before a checkout of $url"
    printf '%s\n' "$rev"
    ;;
  describe)
    # A dependency that names its version by `git describe` gets the ref
    # the build checked out, which is a tag when the build asked for one.
    { IFS= read -r _; IFS= read -r _; IFS= read -r ref || ref=; } < "$dir/$marker"
    [ -n "$ref" ] || die "git describe before a checkout of $url"
    printf '%s\n' "$ref"
    ;;
  submodule)
    # The checkout holds every submodule. A `submodule update` that names
    # paths, from a GIT_SUBMODULES list, leaves the others out.
    paths=()
    for arg in "${rest[@]:1}"; do
      case "$arg" in -*) ;; *) paths+=("$arg") ;; esac
    done
    if [ "${rest[0]:-}" = update ] && [ "${#paths[@]}" -gt 0 ]; then
      bash "$CMAKE_PURIFIER_PRUNE" "$dir" "${paths[@]}"
    fi
    ;;
  fetch | config | status | remote | reset | stash) ;;
  symbolic-ref | show-ref) exit 1 ;;
  *) die "git $sub is not supported on the locked checkout of $url in $dir" ;;
esac
