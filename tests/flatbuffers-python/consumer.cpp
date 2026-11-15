#include <main_generated.h>
#include <flatbuffers/verifier.h>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>
int main(int argc, char** argv) {
  if (argc == 2) {
    std::ifstream input(argv[1], std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    flatbuffers::Verifier verifier(bytes.data(), bytes.size());
    if (!proof::VerifyEnvelopeBuffer(verifier)) return 3;
    if (proof::GetEnvelope(bytes.data())->value()->answer() != 42) return 4;
    std::puts("42");
    return 0;
  }
  static_assert(sizeof(decltype(((proof::Value*)nullptr)->answer())) * 8 == EXPECT_BITS);
  flatbuffers::FlatBufferBuilder builder;
  auto value = proof::CreateValue(builder, 42);
  auto envelope = proof::CreateEnvelope(builder, value);
  proof::FinishEnvelopeBuffer(builder, envelope);
  flatbuffers::Verifier verifier(builder.GetBufferPointer(), builder.GetSize());
  if (!proof::VerifyEnvelopeBuffer(verifier)) return 1;
  if (proof::GetEnvelope(builder.GetBufferPointer())->value()->answer() != 42) return 2;
  std::printf("42:%d:", EXPECT_BITS);
  for (size_t i = 0; i < builder.GetSize(); ++i) std::printf("%02x", builder.GetBufferPointer()[i]);
  std::puts("");
}
