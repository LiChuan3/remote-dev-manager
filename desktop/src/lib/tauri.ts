import { invoke } from "@tauri-apps/api/core"

/** Default sidecar port used when not running inside Tauri. */
const FALLBACK_SIDECAR_PORT = 8765

/**
 * Resolve the local sidecar HTTP port from the Tauri backend.
 * Falls back to {@link FALLBACK_SIDECAR_PORT} outside a Tauri context.
 */
export async function getSidecarPort(): Promise<number> {
  try {
    const port = await invoke<number>("get_sidecar_port")
    return typeof port === "number" && port > 0 ? port : FALLBACK_SIDECAR_PORT
  } catch {
    return FALLBACK_SIDECAR_PORT
  }
}

/** Ask the Tauri backend to quit the app. No-op outside a Tauri context. */
export async function quitApp(): Promise<void> {
  try {
    await invoke("quit_app")
  } catch {
    // no-op in a plain browser context
  }
}
