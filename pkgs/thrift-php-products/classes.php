<?php
// SPDX-License-Identifier: MIT
require $argv[1];
$paths = json_decode(file_get_contents($argv[2]), true, 512, JSON_THROW_ON_ERROR);
$result = [];
foreach ($paths as $path) {
    $map = Composer\Autoload\ClassMapGenerator::createMap($path);
    foreach ($map as $class => $file) {
        $key = strtolower($class);
        if (isset($result[$key]) && realpath($result[$key]['file']) !== realpath($file)) {
            throw new RuntimeException('native PHP class collision: '.$class);
        }
        $result[$key] = ['class' => $class, 'file' => realpath($file)];
    }
}
ksort($result);
echo json_encode($result, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
