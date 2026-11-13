use strict;
use warnings;
use JSON::PP;
use Thrift;
use Thrift::BinaryProtocol;
use Thrift::MemoryBuffer;
use SchemaMain::Types;
use SchemaValue::Types;
use SchemaMain::AnswerService;

my $value = SchemaMain::Envelope->new({value => SchemaValue::Value->new({answer => 42})});
my $buffer = Thrift::MemoryBuffer->new();
$value->write(Thrift::BinaryProtocol->new($buffer));
my $wire = unpack('H*', $buffer->getBuffer());
die "unexpected native wire $wire" unless $wire eq ($ARGV[0] // '0c00010800010000002a0000');
my $input = Thrift::MemoryBuffer->new();
$input->write($buffer->getBuffer());
my $decoded = SchemaMain::Envelope->new();
$decoded->read(Thrift::BinaryProtocol->new($input));
die 'read failed' unless $decoded->value->answer == 42;
my $request = Thrift::MemoryBuffer->new();
my $response = Thrift::MemoryBuffer->new();
my $client = SchemaMain::AnswerServiceClient->new(Thrift::BinaryProtocol->new($response), Thrift::BinaryProtocol->new($request));
$client->send_answer(1);
my $processor = SchemaMain::AnswerServiceProcessor->new(bless({}, 'ProofHandler'));
$processor->process(Thrift::BinaryProtocol->new($request), Thrift::BinaryProtocol->new($response));
my $answer = $client->recv_answer();
die 'RPC failed' unless $answer == 43;
my %origins = map { $_ => $INC{$_} } qw(Thrift.pm Thrift/BinaryProtocol.pm Class/Accessor.pm Bit/Vector.pm SchemaMain/Types.pm SchemaValue/Types.pm SchemaMain/AnswerService.pm);
for my $name (keys %origins) { die "unbound module $name" unless defined $origins{$name}; }
print JSON::PP->new->canonical->pretty->encode({answer => 42, rpc => $answer, wire => $wire, runtimeVersion => "$Thrift::VERSION", origins => \%origins});
package ProofHandler;
sub answer { return 42 + $_[1]; }
