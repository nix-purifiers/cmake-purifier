# SPDX-License-Identifier: MIT
use strict;
use warnings;
use JSON::PP;
use Config;
use version;
use Thrift;
use CPAN::Meta::Requirements;
my ($metadata_path, $compiler_version) = @ARGV;
open my $file, '<', $metadata_path or die $!;
my $metadata = decode_json(do { local $/; <$file> });
$compiler_version =~ /^Thrift version (\d+\.\d+\.\d+)$/ or die 'unknown native compiler version';
die 'compiler and Perl runtime differ' unless version->parse($1) == $Thrift::VERSION;
my $requirements = CPAN::Meta::Requirements->from_string_hash($metadata->{prereqs}{runtime}{requires});
my %dependencies;
for my $module (sort keys %{$metadata->{prereqs}{runtime}{requires}}) {
    my ($installed, $origin);
    if ($module eq 'perl') { $installed = "$^V"; $origin = $^X; }
    else {
        die 'invalid native dependency module' unless $module =~ /^[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*$/;
        my $path = $module; $path =~ s{::}{/}g; $path .= '.pm';
        require $path;
        $installed = $module->VERSION // 0;
        $origin = $INC{$path};
    }
    die "native requirement not satisfied: $module" unless $requirements->accepts_module($module, $installed);
    $dependencies{$module} = {version => "$installed", origin => $origin};
}
my %config = map { $_ => $Config{$_} } qw(version archname useithreads usemultiplicity api_versionstring ivsize ptrsize byteorder);
print JSON::PP->new->canonical->pretty->encode({
    compilerVersion => $compiler_version, nativeVersion => $Thrift::VERSION->numify,
    nativeVersionString => "$Thrift::VERSION", nativeMetadata => $metadata,
    perl => $^X, config => \%config, dependencies => \%dependencies,
});
