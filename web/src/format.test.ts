import { describe, expect, it } from "vitest"
import { fmtSize } from "./format"

describe("fmtSize", () => {
  it("formats space saved as MB below a gigabyte and GB above", () => {
    expect(fmtSize(262_000_000)).toBe("262 MB")
    expect(fmtSize(2_100_000_000)).toBe("2.1 GB")
    expect(fmtSize(0)).toBe("0 MB")
    expect(fmtSize(999_000_000)).toBe("999 MB")
    expect(fmtSize(1_000_000_000)).toBe("1.0 GB")
  })
})
