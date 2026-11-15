#include "main.capnp.h"
#include <capnp/message.h>
#include <capnp/serialize.h>
#include <capnp/schema.h>
#include <dlfcn.h>
#include <cstdio>
#include <cstring>
int main(int argc, char** argv) {
  if (argc != 3) return 9;
  capnp::MallocMessageBuilder message;
  auto envelope = message.initRoot<proof::Envelope>();
  envelope.initValue().setAnswer(42);
  auto words = capnp::messageToFlatArray(message);
  capnp::FlatArrayMessageReader reader(words.asPtr());
  if (reader.getRoot<proof::Envelope>().getValue().getAnswer() != 42) return 1;
  Dl_info owned{}, sdk{};
  if (!dladdr(capnp::_::rawSchema<proof::Value>().encodedNode, &owned)) return 2;
  if (!dladdr(capnp::_::rawSchema<capnp::schema::CodeGeneratorRequest>().encodedNode, &sdk)) return 3;
  if (!std::strstr(owned.dli_fname, argv[1]) || !std::strstr(sdk.dli_fname, argv[2])) return 4;
  std::printf("42:%llu:%s:%s:", (unsigned long long)capnp::Schema::from<proof::Value>().getProto().getId(), owned.dli_fname, sdk.dli_fname);
  for (auto byte : words.asBytes()) std::printf("%02x", byte);
  std::puts("");
}
