import { useEffect } from "react"

/**
 * Captures document clicks on anchors that resolve to an external URL and
 * opens them via the Tauri opener plugin (system browser / mail client)
 * instead of navigating the webview. No-ops in a plain browser context.
 */
export function ExternalLinkGuard() {
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      // Ignore modified / non-primary clicks.
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return
      }

      const target = event.target as Element | null
      const anchor = target?.closest?.("a")
      if (!anchor) return

      // Skip download links and pure in-page anchors.
      if (anchor.hasAttribute("download")) return
      const rawHref = anchor.getAttribute("href")
      if (!rawHref || rawHref.startsWith("#")) return

      const href = anchor.href // resolved absolute URL
      if (!href) return

      let isExternal = false
      try {
        const url = new URL(href, window.location.href)
        if (
          url.protocol === "mailto:" ||
          url.protocol === "tel:"
        ) {
          isExternal = true
        } else if (url.protocol === "http:" || url.protocol === "https:") {
          isExternal = url.origin !== window.location.origin
        }
      } catch {
        return
      }

      if (!isExternal) return

      event.preventDefault()
      void (async () => {
        try {
          const { openUrl } = await import("@tauri-apps/plugin-opener")
          await openUrl(href)
        } catch {
          // Not running inside Tauri (or plugin unavailable): no-op.
        }
      })()
    }

    document.addEventListener("click", onClick, true)
    return () => document.removeEventListener("click", onClick, true)
  }, [])

  return null
}
