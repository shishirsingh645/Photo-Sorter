import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// Testing Library only auto-registers its cleanup when vitest runs with `globals: true`, and this
// project imports describe/it/expect explicitly instead. Without this, every render stays in the
// document and the next test in the same file sees "found multiple elements".
afterEach(cleanup)
