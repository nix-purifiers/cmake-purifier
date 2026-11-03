# Commands

Every command runs from the repository root.

| Command | What it does |
|---|---|
| `nix flake check` | Runs the flake checks in the sandbox (see `testing.md`). |
| `nix fmt` | Formats the Nix files. |
| `nix build '.#cmake-purifier'` | Builds the `cmake-purifier` command. |
| `nix flake check --all-systems --no-build` | Evaluates the checks of every system. |
| `tests/relock-fixtures.sh` | Relocks every fixture. Needs the network. |
| `tests/offline.sh` | Prefetches the fixtures and runs their development loop offline. |
| `tests/update.sh` | Checks that `lock` keeps moved branches and `update` moves them. |
| `tests/negative.sh` | Runs the command tests: errors, `--lockfile` and `publish`. |
