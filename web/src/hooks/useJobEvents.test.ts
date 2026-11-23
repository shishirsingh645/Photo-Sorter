import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { AppState } from "../api/client"
import { useJobEvents } from "./useJobEvents"

class FakeEventSource {
  static all: FakeEventSource[] = []
  onopen: ((e: Event) => void) | null = null
  onmessage: ((e: MessageEvent<string>) => void) | null = null
  onerror: ((e: Event) => void) | null = null
  closed = false
  constructor(readonly url: string) {
    FakeEventSource.all.push(this)
  }
  close() {
    this.closed = true
  }
}

const STATE = { job: { running: true, step: "sort" } } as unknown as AppState
const fetchMock = vi.fn()
const onEvent = vi.fn()
const current = () => FakeEventSource.all[FakeEventSource.all.length - 1]
const open = () => act(() => current().onopen?.(new Event("open")))
const drop = () => act(() => current().onerror?.(new Event("error")))
const wait = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)))

/** A stream that was up and drops, then `n` reconnects (each 900 ms after the last failure) that all fail. */
async function dropThenFailReconnects(n: number) {
  const hook = renderHook(() => useJobEvents(onEvent))
  open()
  await drop()
  for (let i = 0; i < n; i++) {
    await wait(900)
    await drop()
  }
  return hook
}

describe("useJobEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.all = []
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => STATE })
    vi.stubGlobal("EventSource", FakeEventSource)
    vi.stubGlobal("fetch", fetchMock)
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    fetchMock.mockReset()
    onEvent.mockReset()
  })

  it("hands parsed events on, ignores junk frames, and reconnects 900 ms after a drop", async () => {
    renderHook(() => useJobEvents(onEvent))
    open()
    act(() => current().onmessage?.({ data: '{"type":"log","message":"hi"}' } as MessageEvent<string>))
    act(() => current().onmessage?.({ data: ": not json" } as MessageEvent<string>))
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ type: "log", message: "hi" })

    const first = current()
    await drop()
    expect(first.closed).toBe(true)
    await wait(899)
    expect(FakeEventSource.all).toHaveLength(1)
    await wait(1)
    expect(FakeEventSource.all).toHaveLength(2)
    expect(current().url).toBe("/api/events")
  })

  it("falls back to polling after three failed reconnects", async () => {
    // Two failed reconnects are not enough, however long we wait.
    const hook = await dropThenFailReconnects(2)
    await wait(899)
    expect(fetchMock).not.toHaveBeenCalled()
    hook.unmount()
    FakeEventSource.all = []

    // The third failed reconnect starts the poll: first tick 900 ms later, then every 900 ms.
    await dropThenFailReconnects(3)
    await wait(899)
    expect(fetchMock).not.toHaveBeenCalled()
    await wait(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe("/api/state")
    expect(onEvent).toHaveBeenCalledWith({ type: "snapshot", state: STATE })
    await wait(1800)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it("stops polling once the stream comes back", async () => {
    await dropThenFailReconnects(3)
    await wait(900)
    expect(fetchMock).toHaveBeenCalled() // polling is running

    open() // the reconnect that was waiting in the background succeeds
    await wait(0) // one resync of the whole state, for events missed while the stream was down
    const settled = fetchMock.mock.calls.length
    await wait(9000)
    expect(fetchMock.mock.calls.length).toBe(settled)
  })

  it("closes the stream and every timer when the component unmounts", async () => {
    const { unmount } = await dropThenFailReconnects(3)
    const stream = current()
    const streams = FakeEventSource.all.length
    unmount()
    expect(stream.closed).toBe(true)
    await wait(9000)
    expect(FakeEventSource.all).toHaveLength(streams)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
