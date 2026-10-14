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
    let mut virtual_input = false;
    let mut replay = None;
    while let Some(option) = args.next() {
        match option.as_str() {
            "--virtual-input" if !virtual_input => virtual_input = true,
            "--wake-replay" if replay.is_none() => {
                let python = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("python required"))?,
                );
                let manifest = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("manifest required"))?,
                );
                let fixture = args
                    .next()
                    .ok_or_else(|| io::Error::other("fixture required"))?
                    .parse()
                    .map_err(|_| io::Error::other("invalid fixture index"))?;
                if !python.is_absolute() || !manifest.is_absolute() {
                    return Err(io::Error::other("absolute replay paths required"));
                }
                replay = Some(transport::WakeReplay {
                    python,
                    manifest,
                    fixture,
                    active_phrase: None,
                });
            }
            _ => return Err(io::Error::other("unknown or duplicate option")),
        }
    }
    transport::serve(Storage::open(&root)?, virtual_input, replay).await
}
