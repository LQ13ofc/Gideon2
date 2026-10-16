use gideon_base::{storage::Storage, transport};
use std::{io, path::PathBuf};
#[tokio::main(flavor = "current_thread")]
async fn main() -> io::Result<()> {
    let mut args = std::env::args().skip(1);
    if args.next().as_deref() != Some("--root") {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "usage: gideon-base --root ABSOLUTE_PRIVATE_ROOT [--virtual-input] [--home ABSOLUTE_DIR] [--plugin-python ABSOLUTE_PYTHON] [--net-allow-loopback (test only)]",
        ));
    }
    let root = PathBuf::from(
        args.next()
            .ok_or_else(|| io::Error::other("root required"))?,
    );
    let mut virtual_input = false;
    let mut replay = None;
    let mut commands_sandbox = false;
    let mut tts = None;
    let mut base_pack = None;
    let mut hub_catalog = None;
    let mut home = None;
    let mut plugin_python = None;
    let mut net_allow_loopback = false;
    while let Some(option) = args.next() {
        match option.as_str() {
            "--home" if home.is_none() => {
                let path = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("invalid --home"))?,
                );
                home = Some(path);
            }
            "--hub-catalog" if hub_catalog.is_none() => {
                let path = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("Hub catalog required"))?,
                );
                let digest = args
                    .next()
                    .ok_or_else(|| io::Error::other("Hub checksum required"))?;
                if !path.is_absolute() {
                    return Err(io::Error::other("absolute Hub path required"));
                }
                hub_catalog = Some((path, digest));
            }
            "--base-pack" if base_pack.is_none() => {
                let path = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("Base pack required"))?,
                );
                if !path.is_absolute() {
                    return Err(io::Error::other("absolute pack path required"));
                }
                base_pack = Some(path);
            }
            "--plugin-python" if plugin_python.is_none() => {
                let path = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("plugin python required"))?,
                );
                if !path.is_absolute() || !path.is_file() {
                    return Err(io::Error::other("absolute plugin python required"));
                }
                plugin_python = Some(path);
            }
            // Test/dev only: lets the LLM broker reach loopback HTTP servers. Never set in packages.
            "--net-allow-loopback" if !net_allow_loopback => net_allow_loopback = true,
            "--virtual-input" if !virtual_input => virtual_input = true,
            "--commands-sandbox" if !commands_sandbox => commands_sandbox = true,
            "--tts-virtual" if tts.is_none() => {
                let python =
                    PathBuf::from(args.next().ok_or_else(|| io::Error::other("TTS python"))?);
                let manifest = PathBuf::from(
                    args.next()
                        .ok_or_else(|| io::Error::other("TTS manifest"))?,
                );
                if !python.is_absolute() || !manifest.is_absolute() {
                    return Err(io::Error::other("absolute TTS paths required"));
                }
                tts = Some(gideon_base::tts::Config { python, manifest });
            }
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
    if let Some(path) = home {
        transport::set_home(path)?;
    }
    if tts.is_some() && !commands_sandbox {
        return Err(io::Error::other("TTS requires command profile"));
    }
    transport::serve(
        Storage::open_for_runtime(&root)?,
        virtual_input,
        replay,
        commands_sandbox,
        tts,
        base_pack,
        hub_catalog,
        plugin_python,
        net_allow_loopback,
    )
    .await
}
