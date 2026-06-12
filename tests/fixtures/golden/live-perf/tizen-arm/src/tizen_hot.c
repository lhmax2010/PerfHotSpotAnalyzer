int owned_callback(int n) {
  return n + 7;
}

int tizen_hot(int n) {
  int acc = 0;
  for (int i = 0; i < n; ++i) {
    acc += owned_callback(i);
  }
  return acc;
}

int entry_point(int n) {
  return tizen_hot(n);
}
