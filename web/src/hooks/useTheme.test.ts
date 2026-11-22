import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import { useTheme } from "./useTheme"

function systemPrefers(dark: boolean) {
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({
    matches: dark && q.includes("dark"),
    media: q,
  })) as unknown as typeof window.matchMedia
}

describe("useTheme", () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })
  afterEach(() => vi.restoreAllMocks())

  it("defaults to the system preference when nothing is stored", () => {
    systemPrefers(true)
    expect(renderHook(() => useTheme()).result.current.theme).toBe("dark")
    systemPrefers(false)
    expect(renderHook(() => useTheme()).result.current.theme).toBe("light")
  })

  it("restores the stored theme over the system preference", () => {
    systemPrefers(true)
    localStorage.setItem("theme", "light")
    expect(renderHook(() => useTheme()).result.current.theme).toBe("light")
  })

  it("writes data-theme onto the document element", () => {
    systemPrefers(true)
    const { result } = renderHook(() => useTheme())
    expect(document.documentElement.dataset.theme).toBe("dark")
    act(() => result.current.toggle())
    expect(document.documentElement.dataset.theme).toBe("light")
    expect(localStorage.getItem("theme")).toBe("light")
  })

  it("survives localStorage throwing in private mode", () => {
    systemPrefers(true)
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied")
    })
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied")
    })
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe("dark")
    act(() => result.current.toggle())
    expect(result.current.theme).toBe("light")
    expect(document.documentElement.dataset.theme).toBe("light")
  })
})
