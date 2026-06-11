#include <stdint.h>

#ifndef INFLATE_BYTES
#define INFLATE_BYTES 2048
#endif

__attribute__((section(".inflate"), used)) const uint8_t inflate[INFLATE_BYTES] = {1};
__attribute__((section(".steady"), used)) const uint8_t steady[1024] = {2};

int main(void) {
  return inflate[0] + steady[0];
}
