#include <zlib.h>
#include "proof.h"
int answer(void) { return zlibVersion()[0] ? 42 : 0; }
const char *proof_zlib_version(void) { return zlibVersion(); }
const void *proof_zlib_address(void) { return (const void *)zlibVersion; }
