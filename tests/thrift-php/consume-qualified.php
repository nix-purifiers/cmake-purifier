<?php
declare(strict_types=1);

$runtime = $argv[1];
$schema = $runtime;
require $runtime . '/vendor/autoload.php';

use Proof\Main\Envelope;
use Proof\Common\Value;
use Proof\Main\AnswerServiceClient;
use Proof\Main\AnswerServiceIf;
use Proof\Main\AnswerServiceProcessor;
use Thrift\Protocol\TBinaryProtocol;
use Thrift\Transport\TMemoryBuffer;

$value = new Envelope(['value' => new Value(['answer' => 42])]);
$buffer = new TMemoryBuffer();
$value->write(new TBinaryProtocol($buffer));
$wire = $buffer->getBuffer();
if (bin2hex($wire) !== ($argv[2] ?? '0c00010800010000002a0000')) {
    throw new RuntimeException('wire differs from the native C++/Rust fixture');
}
$decoded = new Envelope();
$decoded->read(new TBinaryProtocol(new TMemoryBuffer($wire)));
if ($decoded->value?->answer !== 42) {
    throw new RuntimeException('native PHP reader did not recover the value');
}

$request = new TMemoryBuffer();
$response = new TMemoryBuffer();
$client = new AnswerServiceClient(new TBinaryProtocol($response), new TBinaryProtocol($request));
$handler = new class implements AnswerServiceIf {
    public function answer(?int $delta): ?int { return 42 + $delta; }
};
$client->send_answer(1);
$processor = new AnswerServiceProcessor($handler);
if (!$processor->process(new TBinaryProtocol($request), new TBinaryProtocol($response))) {
    throw new RuntimeException('native generated processor rejected the RPC');
}
$answer = $client->recv_answer();
if ($answer !== 43) {
    throw new RuntimeException('native generated client did not receive the RPC result');
}

$origins = [];
foreach ([Envelope::class, TBinaryProtocol::class, Psr\Log\LoggerInterface::class, Http\Discovery\Psr17FactoryDiscovery::class] as $name) {
    $file = (new ReflectionClass($name))->getFileName();
    if (!$file || (!str_starts_with($file, $runtime . '/') && !str_starts_with($file, $schema . '/'))) {
        throw new RuntimeException('autoload escaped the declared native/generated inputs: ' . $name);
    }
    $origins[$name] = $file;
}
echo json_encode(['answer' => 42, 'rpc' => $answer, 'wire' => bin2hex($wire), 'origins' => $origins, 'nativeSdkVersion' => Composer\InstalledVersions::getPrettyVersion('apache/thrift')], JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR), "\n";
