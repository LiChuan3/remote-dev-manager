# App Icons

This directory holds the generated icon set referenced by `tauri.conf.json`
(`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.icns`, `icon.ico`, and the
Windows Store `Square*Logo.png` / `StoreLogo.png` variants).

**Do not hand-craft these files.** Generate the full set from a single square
source image (1024x1024 PNG recommended) with the Tauri CLI:

```bash
# Run from the `desktop/` directory (where package.json lives):
npm run tauri icon path/to/app-icon.png
```

This command writes all platform icon variants into `src-tauri/icons/`.

The packaging / orchestration step is responsible for running this command
before `cargo build` / `tauri build`, so the binary icons are intentionally
absent from version control until then.
