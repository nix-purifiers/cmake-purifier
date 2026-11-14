include "common/value.thrift"
namespace py main_value
struct Envelope { 1: value.Value value }
service AnswerService { i32 answer(1: i32 delta) }
