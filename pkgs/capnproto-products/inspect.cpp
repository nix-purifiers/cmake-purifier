#include <capnp/serialize.h>
#include <capnp/schema.capnp.h>
#include <capnp/compat/json.h>
#include <iostream>
#include <unistd.h>
int main() {
  capnp::StreamFdMessageReader reader(STDIN_FILENO);
  auto request = reader.getRoot<capnp::schema::CodeGeneratorRequest>();
  capnp::JsonCodec codec;
  auto version = request.getCapnpVersion();
  std::cout << "{\"version\":\"" << unsigned(version.getMajor()) << "." << unsigned(version.getMinor()) << "." << unsigned(version.getMicro()) << "\",\"files\":[";
  bool first = true;
  for (auto node : request.getNodes()) {
    if (!node.isFile()) continue;
    if (!first) std::cout << ",";
    first = false;
    auto name = codec.encode(node.getDisplayName());
    std::cout << "{\"id\":\"" << node.getId() << "\",\"name\":" << name.cStr() << "}";
  }
  std::cout << "],\"requested\":[";
  first = true;
  for (auto file : request.getRequestedFiles()) {
    if (!first) std::cout << ",";
    first = false;
    auto name = codec.encode(file.getFilename());
    std::cout << "{\"id\":\"" << file.getId() << "\",\"name\":" << name.cStr() << ",\"imports\":[";
    bool firstImport = true;
    for (auto import : file.getImports()) {
      if (!firstImport) std::cout << ",";
      firstImport = false;
      auto imported = codec.encode(import.getName());
      std::cout << "{\"id\":\"" << import.getId() << "\",\"name\":" << imported.cStr() << "}";
    }
    std::cout << "]}";
  }
  std::cout << "]}\n";
}
