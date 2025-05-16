#[allow(warnings)]
mod bindings;

use bindings::exports::wasi::cli::run::Guest;

struct Component;

impl Guest for Component {
    fn run() -> Result<(),()> {
        println!("Hello from Rust WASM!");
        Ok(())
    }
}

bindings::export!(Component with_types_in bindings);
