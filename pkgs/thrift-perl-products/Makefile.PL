# SPDX-License-Identifier: MIT
use strict;
use warnings;
use ExtUtils::MakeMaker;
use JSON::PP;
open my $file, '<', 'package.json' or die $!;
my $metadata = decode_json(do { local $/; <$file> });
WriteMakefile(
    NAME => $metadata->{name},
    VERSION => $metadata->{version},
    PREREQ_PM => { 'Thrift' => $metadata->{runtimeVersion}, 'Class::Accessor' => 0 },
);
