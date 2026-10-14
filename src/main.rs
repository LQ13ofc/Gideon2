use gideon_base::{storage::Storage, transport};
use std::{io, path::PathBuf};
#[tokio::main(flavor = "current_thread")]
async fn main() -> io::Result<()> {
    let mut args = std::env::args().skip(1);
    if args.next().as_deref() != Some("--root") {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "usage: gideon-base --root ABSOLUTE_PRIVATE_ROOT [--virtual-input]",
        ));
    }
    let root = PathBuf::from(
        args.next()
            .ok_or_else(|| io::Error::other("root required"))?,
    );
    let virtual_input = match args.next().as_deref() {
        None => false,
        Some("--virtual-input") => true,
        _ => return Err(io::Error::other("unknown option")),
    };
    if args.next().is_some() {
        return Err(io::Error::other("unexpected argument"));
    }
    transport::serve(Storage::open(&root)?, virtual_input).await
}
