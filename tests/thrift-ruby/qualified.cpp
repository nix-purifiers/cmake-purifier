// SPDX-License-Identifier: MIT
#include <root_types.h>
#include <thrift/protocol/TBinaryProtocol.h>
#include <thrift/transport/TBufferTransports.h>
#include <iomanip>
#include <iostream>
#include <memory>
int main() {
  first_value::Value left; left.__set_answer(7);
  second_value::Value right; right.__set_answer(8);
  root_value::Pair pair; pair.__set_left(left); pair.__set_right(right);
  auto buffer = std::make_shared<apache::thrift::transport::TMemoryBuffer>();
  apache::thrift::protocol::TBinaryProtocol protocol(buffer);
  pair.write(&protocol);
  uint8_t* bytes = nullptr; uint32_t size = 0; buffer->getBuffer(&bytes, &size);
  for (uint32_t i=0; i<size; ++i) std::cout << std::hex << std::setfill('0') << std::setw(2) << unsigned(bytes[i]);
  std::cout << '\n';
}
