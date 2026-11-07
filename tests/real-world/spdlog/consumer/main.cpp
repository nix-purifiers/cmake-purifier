#include <spdlog/spdlog.h>
#include <spdlog/sinks/ostream_sink.h>
#include <sstream>
int main() {
  std::ostringstream output;
  auto sink = std::make_shared<spdlog::sinks::ostream_sink_mt>(output);
  spdlog::logger logger("proof", sink);
  logger.set_pattern("%v");
  logger.info("answer {}", 42);
  return output.str() == "answer 42\n" ? 0 : 1;
}
