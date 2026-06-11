#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint64_t busy_loop(uint64_t iterations) {
  volatile uint64_t total = 0;
  for (uint64_t i = 0; i < iterations; ++i) {
    total += (i * 2654435761u) ^ (total >> 3);
  }
  return total;
}

static uint64_t helper_spin(uint64_t iterations) {
  volatile uint64_t total = 1;
  for (uint64_t i = 0; i < iterations / 8; ++i) {
    total += i + (total << 1);
  }
  return total;
}

int main(int argc, char **argv) {
  uint64_t iterations = 4000000;
  if (argc > 1) {
    iterations = strtoull(argv[1], NULL, 10);
  }
  uint64_t total = busy_loop(iterations);
  total += helper_spin(iterations);
  printf("%llu\n", (unsigned long long)total);
  return 0;
}
