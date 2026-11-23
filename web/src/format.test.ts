import { describe, expect, it } from "vitest"
import { fmt, fmtSize } from "./format"

describe("fmtSize", () => {
  it("formats space saved as MB below a gigabyte and GB above", () => {
    expect(fmtSize(262_000_000)).toBe("262 MB")
    expect(fmtSize(2_100_000_000)).toBe("2.1 GB")
    expect(fmtSize(0)).toBe("0 MB")
    expect(fmtSize(999_000_000)).toBe("999 MB")
    expect(fmtSize(1_000_000_000)).toBe("1.0 GB")
  })
})

describe("fmt", () => {
  it("writes whole numbers with thousands separators, rounding fractions", () => {
    expect(fmt(1136)).toBe("1,136")
    expect(fmt(71.04)).toBe("71")
    expect(fmt(0)).toBe("0")
    expect(fmt(1_234_567)).toBe("1,234,567")
  })
})
