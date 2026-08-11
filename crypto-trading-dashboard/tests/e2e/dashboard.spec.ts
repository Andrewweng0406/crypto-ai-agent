import { expect, test } from "@playwright/test"
import { mockDashboardApis } from "./api-mocks"

test.beforeEach(async ({ page }) => {
  await mockDashboardApis(page)
})

test("overview renders production data surfaces without mock placeholders", async ({ page }) => {
  await page.goto("/")

  await expect(page.getByText("Weng Crypto")).toBeVisible()
  await expect(page.getByText("AI Risk & Decision Terminal")).toBeVisible()
  await expect(page.getByText("資金風控")).toBeVisible()
  await expect(page.getByText("交易日記")).toBeVisible()
  await expect(page.getByText("BTC")).toBeVisible()
  await expect(page.getByText("等回踩")).toBeVisible()
  await expect(page.getByText("主流幣/市場掃描")).toBeVisible()
  await expect(page.getByRole("heading", { name: "美股 ORB" })).toBeVisible()

  await expect(page.getByText(/mock/i)).toHaveCount(0)
  await expect(page.getByText(/demo/i)).toHaveCount(0)
  await expect(page.getByText(/sample trade/i)).toHaveCount(0)
})

test("risk settings persist through the backend and cap position size", async ({ page }) => {
  const putRequests: unknown[] = []
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().includes("/api/risk-settings")) {
      putRequests.push(request.postDataJSON())
    }
  })

  await page.goto("/")

  await expect(page.getByLabel("帳戶資金")).toHaveValue("1000")
  await page.getByLabel("帳戶資金").fill("2000")
  await page.getByLabel("單筆風險 %").fill("2")
  await page.getByLabel("最大槓桿").fill("3")
  await page.getByLabel("進場價").fill("100")
  await page.getByLabel("停損價").fill("95")

  await expect.poll(() => putRequests.length).toBeGreaterThan(0)
  await expect
    .poll(() => putRequests.at(-1))
    .toMatchObject({ account_size: 2000, risk_pct: 2, max_leverage: 3 })
  await expect(page.getByText("$800.00")).toBeVisible()
  await expect(page.getByText("未觸發")).toBeVisible()
})

test("main tabs work on desktop and mobile without horizontal overflow", async ({ page }) => {
  await page.goto("/")

  await page.getByRole("button", { name: "加密貨幣" }).click()
  await page.getByRole("button", { name: "主流幣" }).click()
  await expect(page.getByRole("heading", { name: "BTC/USDT:USDT" })).toBeVisible()
  await expect(page.getByText("No Active Signal")).toBeVisible()

  await page.getByRole("button", { name: "美股" }).click()
  await page.getByRole("button", { name: "美股 ORB" }).click()
  await expect(page.getByRole("heading", { name: "TSLA" })).toBeVisible()
  await expect(page.getByText("美股當沖時段")).toBeVisible()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole("button", { name: "總覽", exact: true }).click()
  await expect(page.getByText("AI Risk & Decision Terminal")).toBeVisible()

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
})
