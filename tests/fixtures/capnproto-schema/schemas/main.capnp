@0xa9f3424689d50bcb;
using Cxx = import "/capnp/c++.capnp";
$Cxx.namespace("proof");
using Common = import "common/value.capnp";
struct Envelope { value @0 :Common.Value; }
