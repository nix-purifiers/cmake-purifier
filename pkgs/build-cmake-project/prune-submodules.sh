# SPDX-License-Identifier: MIT
#
# Empties the submodules of a git checkout that a GIT_SUBMODULES list
# leaves out, so that the checkout looks the way git leaves it when it
# initializes only the listed ones: each other submodule is an empty
# directory.
#
#   bash prune-submodules.sh <checkout> <submodule path>...
#
# The submodules are the `path` entries of <checkout>/.gitmodules. The
# script needs bash and coreutils only, since the git shim runs it with
# whatever PATH the build has.
set -eu
shopt -s dotglob nullglob

checkout=$1
shift
[ -f "$checkout/.gitmodules" ] || exit 0

while IFS= read -r line; do
  line=${line#"${line%%[![:space:]]*}"}
  case "$line" in
    path*=*) ;;
    *) continue ;;
  esac
  path=${line#*=}
  path=${path#"${path%%[![:space:]]*}"}
  path=${path%"${path##*[![:space:]]}"}
  keep=
  for listed in "$@"; do
    [ "$listed" = "$path" ] && keep=1
  done
  if [ -z "$keep" ] && [ -d "$checkout/$path" ]; then
    chmod -R u+w "$checkout/$path"
    for entry in "$checkout/$path"/*; do
      rm -rf "$entry"
    done
  fi
done < "$checkout/.gitmodules"
