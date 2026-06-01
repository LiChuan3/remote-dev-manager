import { useEffect } from "react"

function isElement(value: EventTarget | null): value is HTMLElement {
  return value instanceof HTMLElement
}

function canScrollY(el: HTMLElement, deltaY: number): boolean {
  if (Math.abs(deltaY) < 0.5) return false
  if (el.scrollHeight <= el.clientHeight + 1) return false

  const style = window.getComputedStyle(el)
  const overflowY = style.overflowY
  const scrollable =
    overflowY === "auto" ||
    overflowY === "scroll" ||
    overflowY === "overlay" ||
    el.hasAttribute("data-ui-scroll-container")
  if (!scrollable) return false

  if (deltaY > 0) {
    return el.scrollTop + el.clientHeight < el.scrollHeight - 1
  }
  return el.scrollTop > 0
}

function scrollElement(el: HTMLElement, deltaY: number): boolean {
  const before = el.scrollTop
  el.scrollTop += deltaY
  return el.scrollTop !== before
}

function canScrollDocument(deltaY: number): boolean {
  const doc = document.documentElement
  if (doc.scrollHeight <= window.innerHeight + 1) return false
  if (deltaY > 0) {
    return window.scrollY + window.innerHeight < doc.scrollHeight - 1
  }
  return window.scrollY > 0
}

function scrollDocument(deltaY: number): boolean {
  const before = window.scrollY
  window.scrollBy({ top: deltaY, left: 0, behavior: "auto" })
  return window.scrollY !== before
}

function eventPath(event: WheelEvent): EventTarget[] {
  if (typeof event.composedPath === "function") return event.composedPath()
  const path: EventTarget[] = []
  let node: Node | null = event.target as Node | null
  while (node) {
    path.push(node)
    node = node.parentNode
  }
  path.push(window)
  return path
}

export function useWheelScroll() {
  useEffect(() => {
    const onWheel = (event: WheelEvent) => {
      if (event.defaultPrevented || event.ctrlKey || event.metaKey) return
      if (Math.abs(event.deltaY) < Math.abs(event.deltaX)) return

      const path = eventPath(event)
      for (const target of path) {
        if (!isElement(target)) continue
        if (!canScrollY(target, event.deltaY)) continue
        if (scrollElement(target, event.deltaY)) {
          event.preventDefault()
          return
        }
      }

      const main = document.querySelector<HTMLElement>("[data-ui-scroll-container]")
      if (main && canScrollY(main, event.deltaY) && scrollElement(main, event.deltaY)) {
        event.preventDefault()
        return
      }

      if (canScrollDocument(event.deltaY) && scrollDocument(event.deltaY)) {
        event.preventDefault()
      }
    }

    window.addEventListener("wheel", onWheel, { capture: true, passive: false })
    return () => window.removeEventListener("wheel", onWheel, { capture: true })
  }, [])
}
