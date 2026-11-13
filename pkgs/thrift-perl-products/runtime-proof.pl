# SPDX-License-Identifier: MIT
use strict;
use warnings;
use JSON::PP;
use Config;
use version;
use File::Find;
use Digest::SHA qw(sha256_hex);
use Cwd qw(abs_path);
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
my %modules;
my @search_paths;
for my $root (@INC) {
    die 'unsupported native Perl loader hook' if ref($root);
    next unless -d $root;
    push @search_paths, $root;
    File::Find::find({ no_chdir => 1, follow_fast => 1, follow_skip => 2,
        wanted => sub {
            my $path = $File::Find::name;
            return unless -f $path && $path =~ /\.pm$/;
            my $relative = substr($path, length($root) + 1);
            die 'non-relative native module path' unless index($path, "$root/") == 0 && $relative !~ m{(?:^|/)\.\.(?:/|$)};
            open my $module, '<:raw', $path or die $!;
            my $bytes = do { local $/; <$module> };
            push @{$modules{$relative}}, { origin => abs_path($path), searchRoot => $root,
                sha256 => sha256_hex($bytes) };
        }
    }, $root);
}
my %config = map { $_ => $Config{$_} } qw(version archname useithreads usemultiplicity api_versionstring ivsize ptrsize byteorder);
print JSON::PP->new->canonical->pretty->encode({
    compilerVersion => $compiler_version, nativeVersion => $Thrift::VERSION->numify,
    nativeVersionString => "$Thrift::VERSION", nativeMetadata => $metadata,
    perl => $^X, config => \%config, dependencies => \%dependencies,
    moduleSearchPaths => \@search_paths, modules => \%modules,
});
