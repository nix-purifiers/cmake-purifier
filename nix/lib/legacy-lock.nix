# SPDX-License-Identifier: MIT
# Acquisition closure only. No named dependency graph or target projections.
{
  src ? null,
  lockFile,
}:
let
  file = builtins.fromJSON (builtins.readFile lockFile);
  expected = [
    "artifacts"
    "cmakeFlags"
    "contentHash"
    "definitionHash"
    "dependencyMetadataAvailable"
    "nativeProfile"
    "outputs"
    "project"
    "sdk"
    "targetMetadataAvailable"
    "version"
  ];
  sameKeys = object: keys: builtins.isAttrs object && builtins.attrNames object == keys;
  safeRelative =
    path:
    builtins.isString path
    && path != ""
    && builtins.substring 0 1 path != "/"
    && builtins.match ".*\\.\\..*" path == null
    && builtins.match ".*\n.*" path == null;
  safeModuleRoot =
    path:
    builtins.isString path
    && builtins.match "[A-Za-z0-9_+-][A-Za-z0-9_.+-]*(/[A-Za-z0-9_+-][A-Za-z0-9_.+-]*)*" path != null;
  artifactOK =
    entry:
    sameKeys entry [
      "hash"
      "mirrors"
      "path"
      "url"
    ]
    && safeRelative entry.path
    && entry.mirrors == [ ]
    && builtins.match "https?://[^ /]+/.*" entry.url != null
    && builtins.match "sha256-[A-Za-z0-9+/]{43}=" entry.hash != null;
  schemaOK =
    sameKeys file expected
    && file.version == 4
    && file.nativeProfile == "legacy-external-v1"
    && file.dependencyMetadataAvailable == false
    && file.targetMetadataAvailable == false
    && sameKeys file.outputs [ "files" ]
    && builtins.isList file.outputs.files
    && builtins.all safeRelative file.outputs.files
    && builtins.isList file.artifacts
    && file.artifacts != [ ]
    && builtins.all artifactOK file.artifacts
    && sameKeys file.project [
      "name"
      "version"
    ]
    && builtins.isString file.project.name
    && file.project.name != ""
    && file.project.version == ""
    && sameKeys file.sdk [
      "moduleRoot"
      "package"
      "source"
      "version"
    ]
    && safeModuleRoot file.sdk.moduleRoot
    && builtins.isString file.sdk.package
    && builtins.isString file.sdk.version
    && sameKeys file.sdk.source [
      "sha256"
      "url"
    ]
    && builtins.match "[0-9a-f]{64}" file.sdk.source.sha256 != null
    && builtins.isList file.cmakeFlags
    && builtins.all builtins.isString file.cmakeFlags;
  problems =
    if !schemaOK then
      [ "cmake-purifier: invalid legacy acquisition lock schema; restore or relock" ]
    else if
      file.contentHash
      != "sha256:${builtins.hashString "sha256" (builtins.toJSON (removeAttrs file [ "contentHash" ]))}"
    then
      [ "cmake-purifier: legacy lock content hash differs; restore or relock" ]
    else if builtins.isPath src && file.definitionHash != import ./definition-hash.nix src then
      [ "cmake-purifier: legacy lock is older than the project; relock" ]
    else
      [ ];
in
{
  purifier = "cmake-purifier";
  inherit problems;
  entries = if problems == [ ] then file.artifacts else [ ];
  outputs =
    if problems == [ ] then
      {
        ${file.project.name} = file.outputs // {
          targetMetadataAvailable = false;
        };
      }
    else
      { };
  cmake = file;
}
