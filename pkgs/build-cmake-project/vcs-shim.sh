# SPDX-License-Identifier: MIT
#
# The hg, svn and cvs of a build from the lockfile. The initial cache names
# a wrapper around this script in HG_EXECUTABLE, Subversion_SVN_EXECUTABLE
# and CVS_EXECUTABLE, so every checkout that ExternalProject_Add() and
# FetchContent make with one of the three tools goes through it.
#
# The wrapper sets three variables. CMAKE_PURIFIER_VCS is the tool: hg,
# svn or cvs. CMAKE_PURIFIER_VCS_TABLE names the table of its locked
# checkouts, a line per checkout with the repository, the ref the build
# asked for and the store path of the checkout, separated by tabs.
# CMAKE_PURIFIER_REAL_VCS is the real tool, which runs every command this
# script does not answer itself, such as `--version`; it is empty when the
# build has no such tool.
#
# The repository and ref of a checkout are the ones the lock run recorded:
#
# - hg: the URL of `hg clone -U <url> <dir>`, and the tag of the `hg update
#   <tag>` that follows it in <dir>.
# - svn: the URL of `svn co <url> [-r<rev>] ... <dir>`, and its `-r` value,
#   empty when there is none.
# - cvs: `<root> <module>` of `cvs -d <root> co <tag> -d <dir> <module>`, and
#   its tag as `r:<tag>`, `D:<date>`, or empty when there is none.
#
# A checkout copies the locked checkout into <dir> and marks <dir>, and the
# update step that ExternalProject runs in <dir> on every build does
# nothing there. The script needs bash and coreutils only.
set -eu
shopt -s dotglob nullglob

tool=$CMAKE_PURIFIER_VCS
table=$CMAKE_PURIFIER_VCS_TABLE
real=$CMAKE_PURIFIER_REAL_VCS
marker=.cmake-purifier-checkout

die() {
  echo "cmake-purifier: $*" >&2
  exit 1
}

pass() {
  [ -n "$real" ] || die "$tool $* is not supported in a build from the lockfile"
  exec "$real" "$@"
}

# Sets found_path from the table line of repository $1 and ref $2.
lookup() {
  found_path=
  while IFS=$'\t' read -r t_repo t_ref t_path; do
    if [ "$t_repo" = "$1" ] && [ "$t_ref" = "$2" ]; then
      found_path=$t_path
      return 0
    fi
  done < "$table"
  return 1
}

known() {
  while IFS=$'\t' read -r t_repo _ _; do
    [ "$t_repo" = "$1" ] && return 0
  done < "$table"
  return 1
}

unlocked() {
  die "the build checks out $2 of $1 with $tool, which the lockfile does not hold. Run \`cmake-purifier lock\` to lock it."
}

# Copies the locked checkout of repository $2 and ref $3 into directory $1.
place() {
  lookup "$2" "$3" || unlocked "$2" "${3:-the default revision}"
  mkdir -p "$1"
  for entry in "$1"/*; do
    rm -rf "$entry"
  done
  cp -R "$found_path/." "$1/"
  chmod -R u+w "$1"
  printf '%s\n%s\n' "$2" "$found_path" > "$1/$marker"
}

absolute() {
  case "$1" in /*) printf '%s\n' "$1" ;; *) printf '%s\n' "$PWD/$1" ;; esac
}

if [ -f "$PWD/$marker" ]; then
  # The update steps, in a checkout this script placed.
  case "$tool:${1:-}" in
    hg:pull | svn:up | svn:update | cvs:*) exit 0 ;;
    hg:update | hg:up)
      { IFS= read -r repo; } < "$PWD/$marker"
      place "$PWD" "$repo" "${2:-}"
      exit 0
      ;;
  esac
  die "$tool $* is not supported on a locked checkout in $PWD"
fi

case "$tool" in
  hg)
    [ "${1:-}" = clone ] || pass "$@"
    shift
    positional=()
    for arg in "$@"; do
      case "$arg" in -*) ;; *) positional+=("$arg") ;; esac
    done
    [ "${#positional[@]}" -ge 2 ] || pass clone "$@"
    repo=${positional[0]}
    dest=$(absolute "${positional[1]}")
    known "$repo" || unlocked "$repo" "a clone"
    mkdir -p "$dest"
    printf '%s\n' "$repo" > "$dest/$marker"
    ;;
  svn)
    case "${1:-}" in co | checkout) ;; *) pass "$@" ;; esac
    shift
    positional=()
    ref=
    while [ $# -gt 0 ]; do
      case "$1" in
        -r) ref=$2; shift 2 ;;
        -r*) ref=${1#-r}; shift ;;
        -*) shift ;;
        *) positional+=("$1"); shift ;;
      esac
    done
    [ "${#positional[@]}" -ge 2 ] || die "svn checkout without a URL and a directory"
    place "$(absolute "${positional[$((${#positional[@]} - 1))]}")" "${positional[0]}" "$ref"
    ;;
  cvs)
    root=
    while [ $# -gt 0 ]; do
      case "$1" in
        -d) root=$2; shift 2 ;;
        -z) shift 2 ;;
        -*) shift ;;
        *) break ;;
      esac
    done
    case "${1:-}" in co | checkout) ;; *) pass "$@" ;; esac
    shift
    ref=
    dir=
    module=
    while [ $# -gt 0 ]; do
      case "$1" in
        -r) ref=r:$2; shift 2 ;;
        -r*) ref=r:${1#-r}; shift ;;
        -D) ref=D:$2; shift 2 ;;
        -D*) ref=D:${1#-D}; shift ;;
        -d) dir=$2; shift 2 ;;
        -*) shift ;;
        *) module=$1; shift ;;
      esac
    done
    [ -n "$module" ] || die "cvs checkout without a module"
    place "$(absolute "${dir:-$module}")" "$root $module" "$ref"
    ;;
esac
