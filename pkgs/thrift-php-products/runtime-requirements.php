<?php
// SPDX-License-Identifier: MIT
// Resolve the source SDK's own requirements against its actual installation,
// using native Composer package, platform, replacement and constraint APIs.
require $argv[1];
$manifest = json_decode(file_get_contents($argv[2]), true, 512, JSON_THROW_ON_ERROR);
$installed = json_decode(file_get_contents($argv[3]), true, 512, JSON_THROW_ON_ERROR);
$root = json_decode(file_get_contents($argv[4]), true, 512, JSON_THROW_ON_ERROR);
$packages = isset($installed['packages']) ? $installed['packages'] : $installed;
$loader = new Composer\Package\Loader\ArrayLoader();
$repository = new Composer\Repository\InstalledRepository([
    new Composer\Repository\InstalledArrayRepository($loader->loadPackages($packages)),
    new Composer\Repository\PlatformRepository(),
]);
// This is the observed native root version, used only for the native in-memory
// package object. The original SDK manifest is never rewritten.
$manifest['version'] = $root['pretty_version'];
$source = $loader->load($manifest);
$checks = [];
$required = array_merge(array_values($source->getRequires()), array_values($source->getDevRequires()));
foreach ($repository->getPackages() as $package) {
    foreach ($package->getRequires() as $link) {
        $required[] = $link;
    }
}
foreach ($required as $link) {
    $matches = $repository->findPackagesWithReplacersAndProviders($link->getTarget(), $link->getConstraint());
    if (!$matches) {
        throw new RuntimeException('native SDK dependency missing or incompatible: '.$link->getSource().' requires '.$link->getTarget().' '.$link->getPrettyConstraint());
    }
    $checks[] = ['source' => $link->getSource(), 'target' => $link->getTarget(),
        'constraint' => $link->getPrettyConstraint(),
        'providers' => array_map(static fn($package) => $package->getName(), $matches)];
}
echo json_encode($checks, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
