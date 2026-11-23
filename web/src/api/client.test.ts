import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import * as client from "./client"
import { ApiError, UNREACHABLE } from "./client"

// A bare object, not a Response: nothing here depends on the platform's stream machinery.
const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body })
const fetchMock = vi.fn()
const bad = { source: "", dest: "D:/out", labeler: "stub", limit: 0 } as const

async function failure(p: Promise<unknown>): Promise<ApiError> {
  const e = await p.then(
    () => null,
    (x: unknown) => x,
  )
  expect(e).toBeInstanceOf(ApiError)
  return e as ApiError
}

describe("client", () => {
  beforeEach(() => vi.stubGlobal("fetch", fetchMock))
  afterEach(() => {
    vi.unstubAllGlobals()
    fetchMock.mockReset()
  })

  it("surfaces the server's error message verbatim on a 400", async () => {
    fetchMock.mockResolvedValue(reply(400, { error: "Choose the folder with your photos first." }))
    await expect(client.sort(bad)).rejects.toThrow("Choose the folder with your photos first.")
    const e = await failure(client.sort(bad))
    expect(e).toMatchObject({ status: 400, busy: false })
  })

  it("tells a 409 (the file changed) from a 400 (a bad request) by status, and sends the sha", async () => {
    fetchMock.mockResolvedValueOnce(reply(409, { detail: "The folder was rescanned since this page loaded." }))
    const stale = await failure(client.getRecord(7, "abc/123"))
    expect(stale.status).toBe(409)
    expect(stale.message).toBe("The folder was rescanned since this page loaded.")
    expect(fetchMock.mock.calls[0][0]).toBe("/api/record/7?sha=abc%2F123")

    fetchMock.mockResolvedValueOnce(reply(400, { detail: "Missing sha." }))
    expect((await failure(client.getRecord(7, ""))).status).toBe(400)
  })

  it("sends the sha with a move", async () => {
    fetchMock.mockResolvedValue(reply(200, { ok: true }))
    await client.move(3, "food", "sha-3")
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe("/api/move")
    expect(JSON.parse(init.body)).toEqual({ id: 3, key: "food", sha: "sha-3" })
  })

  it("reads the middleware's detail shape and a validation error's list of messages", async () => {
    fetchMock.mockResolvedValueOnce(reply(403, { detail: "This request came from http://evil, so it was blocked." }))
    expect((await failure(client.cancel())).message).toBe("This request came from http://evil, so it was blocked.")
    fetchMock.mockResolvedValueOnce(reply(422, { detail: [{ msg: "Field required" }, { msg: "Input should be a string" }] }))
    expect((await failure(client.peek("x"))).message).toBe("Field required Input should be a string")
  })

  it("flags a second concurrent job as busy, and nothing else as busy", async () => {
    fetchMock.mockResolvedValueOnce(
      reply(400, { error: "A sort job is already running. Stop it before starting another." }),
    )
    expect(await failure(client.sort(bad))).toMatchObject({ status: 400, busy: true })
    fetchMock.mockResolvedValueOnce(reply(400, { error: "Nothing has been scanned yet." }))
    expect((await failure(client.run({ step: "dupes", labeler: "stub", limit: 0 }))).busy).toBe(false)
  })

  it("explains an unreachable server and a body that is not JSON", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"))
    expect(await failure(client.getState())).toMatchObject({ status: 0, message: UNREACHABLE })
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502, json: async () => Promise.reject(new SyntaxError()) })
    expect(await failure(client.getState())).toMatchObject({ status: 502, message: expect.stringContaining("502") })
  })
})
