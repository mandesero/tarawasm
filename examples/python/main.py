from adder import exports

class Run(exports.Run):
    def run(self) -> None:
        print("Hello from Python WASM!")
