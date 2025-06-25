#include "adder.h"
#include <stdio.h>

bool exports_wasi_cli_run_run(void) {
    printf("Hello from C WASM!\n");
    return true;
}
