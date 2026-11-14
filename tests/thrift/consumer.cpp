#include <main_types.h>
#include <AnswerService.h>
#include <thrift/protocol/TBinaryProtocol.h>
#include <thrift/transport/TBufferTransports.h>
#include <thrift/TOutput.h>
#include <dlfcn.h>
#include <cstdio>
#include <memory>
using apache::thrift::protocol::TBinaryProtocol;
using apache::thrift::transport::TMemoryBuffer;
class Handler : public AnswerServiceIf {
 public: int32_t answer(const int32_t delta) override { return 42 + delta; }
};
int main() {
 auto memory = std::make_shared<TMemoryBuffer>();
 TBinaryProtocol protocol(memory);
 Value value; value.__set_answer(42);
 Envelope original; original.__set_value(value);
 original.write(&protocol);
 uint8_t* bytes; uint32_t size; memory->getBuffer(&bytes,&size);
 if(size==0)return 6;
 std::printf("42:");for(uint32_t i=0;i<size;++i)std::printf("%02x",bytes[i]);std::puts("");
 Envelope restored; restored.read(&protocol);
 if (restored.value.answer != 42) return 1;
 auto request=std::make_shared<TMemoryBuffer>(),response=std::make_shared<TMemoryBuffer>();
 auto input=std::make_shared<TBinaryProtocol>(request),output=std::make_shared<TBinaryProtocol>(response);
 AnswerServiceClient client(output,input);
 client.send_answer(1);
 AnswerServiceProcessor processor(std::make_shared<Handler>());
 if(!processor.process(input,output,nullptr))return 2;
 if(client.recv_answer()!=43)return 3;
 Dl_info owned{},sdk{};
 if(!dladdr(*reinterpret_cast<void**>(&original),&owned))return 4;
 if(!dladdr(reinterpret_cast<void*>(&apache::thrift::TOutput::instance),&sdk))return 5;
 std::printf("43\n%s\n%s\n",owned.dli_fname,sdk.dli_fname);
}
