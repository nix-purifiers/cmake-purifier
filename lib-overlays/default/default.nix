# SPDX-License-Identifier: MIT
#
# The `cmake-purifier` library namespace: `readLock` (lib-overlays/default/lock.nix),
# which reads a lockfile into the lock in memory of the purifier contract.
{ ... }:
{

  overlay = final: prev: {
    cmake-purifier = (prev.cmake-purifier or { }) // {
      readLock = import ./lock.nix;
    };
  };

}
