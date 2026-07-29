import { expect, test, type Page, type Route } from "@playwright/test";

const account = {
  id: "11111111-1111-4111-8111-111111111111",
  display_name: "Everyday Savings",
  institution_code: "ICICI",
  account_type: "bank_account",
};
const parentCategory = {
  id: "22222222-2222-4222-8222-222222222222",
  code: "food_drinks",
  name: "Food & Drinks",
  parent_id: null,
  parent_name: null,
};
const childCategory = {
  id: "33333333-3333-4333-8333-333333333333",
  code: "food_drinks_eating_out",
  name: "Eating Out",
  parent_id: parentCategory.id,
  parent_name: parentCategory.name,
};
const transaction = {
  id: "44444444-4444-4444-8444-444444444444",
  transaction_date: "2026-07-28",
  narration: "UPI-DEMO CAFE",
  merchant_normalized: "Demo Cafe",
  provider_reference: "UTR-DEMO-1",
  amount: "850.00",
  currency: "INR",
  direction: "debit",
  account_name: account.display_name,
  category: null,
  category_id: null,
};

function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page) {
  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() !== "GET") return json(route, {});
    if (path === "/api/v1/preferences") return json(route, { reporting_period: "this_month" });
    if (path === "/api/v1/financial-accounts") return json(route, [account]);
    if (path === "/api/v1/categories") return json(route, [parentCategory, childCategory]);
    if (path === "/api/v1/transactions/page") {
      return json(route, { items: [transaction], next_cursor: null });
    }
    if (path === "/api/v1/reports/period") {
      return json(route, {
        income: "50000.00",
        expense: "850.00",
        categories: [{ category: "Food & Drinks", direction: "debit", amount: "850.00" }],
      });
    }
    if (path === "/api/v1/accounts/balance-summary") {
      return json(route, {
        cash_balance: "49150.00",
        credit_card_outstanding: "0",
        net_worth: "49150.00",
        accounts: [{ ...account, balance: "49150.00", currency: "INR" }],
      });
    }
    if (path === "/api/v1/insights/monthly") {
      return json(route, {
        month: "2026-07",
        expense: "850.00",
        forecast: { projected_expense: "941.00", days_observed: 28, days_in_month: 31 },
        anomalies: [],
      });
    }
    if (path === "/api/v1/spending/summary") {
      return json(route, {
        expense: "850.00",
        categories: [{
          category_id: parentCategory.id,
          category: parentCategory.name,
          amount: "850.00",
          percentage: "100.0",
        }],
      });
    }
    if (path.includes("/api/v1/spending/categories/")) {
      return json(route, {
        category_id: parentCategory.id,
        granularity: url.searchParams.get("granularity") ?? "monthly",
        points: [{ period: "2026-07", amount: "850.00" }],
      });
    }
    if (path === "/api/v1/privacy/inventory") {
      return json(route, {
        accounts: 1,
        transactions: 1,
        stored_documents: 0,
        connected_mailboxes: 0,
        retention_policy: { source_artifacts_days: 365, statement_files_days: 730 },
      });
    }
    if (path === "/api/v1/recurring-payments") {
      return json(route, [{
        id: "55555555-5555-4555-8555-555555555555",
        display_name: "Demo subscription",
        account_name: account.display_name,
        category: "Subscriptions",
        cadence: "monthly",
        typical_amount: "499.00",
        monthly_equivalent: "499.00",
        next_expected_on: "2026-08-01",
        confidence: "0.95",
        kind: "subscription",
        occurrence_count: 3,
        state: "confirmed",
      }]);
    }
    return json(route, []);
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByText("₹49,150").first()).toBeVisible();
});

test("dashboard and primary product areas render at supported viewports", async ({ page }) => {
  await expect(page.getByText(/Good (morning|afternoon|evening|night),/)).toBeVisible();
  await expect(page.getByText("Total bank balance")).toBeVisible();

  await page.getByRole("button", { name: "Spending" }).first().click();
  await expect(page.getByRole("heading", { name: "Spending", level: 1 })).toBeVisible();
  await expect(page.getByText("Spending by category")).toBeVisible();

  await page.getByRole("button", { name: "Privacy" }).first().click();
  await expect(page.getByRole("heading", { name: "Privacy", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Source-file retention" })).toBeVisible();
});

test("transaction details and tagging are keyboard safe", async ({ page }) => {
  await page.getByRole("button", { name: "Transactions" }).first().click();
  await page.getByRole("button", { name: /Demo Cafe/ }).click();

  const details = page.getByRole("dialog", { name: "TRANSACTION" });
  await expect(details).toBeVisible();
  await expect(details.getByText("UTR-DEMO-1")).not.toBeVisible();
  await details.getByRole("button", { name: "More details" }).click();
  await expect(details.getByText("UTR-DEMO-1")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(details).not.toBeVisible();

  await page.getByRole("button", { name: "Tag transaction" }).click();
  const tagDialog = page.getByRole("dialog", { name: "Tag transaction" });
  await expect(tagDialog).toBeVisible();
  await tagDialog.getByRole("button", { name: /Eating Out/ }).click();
  const saveCategory = tagDialog.getByRole("button", { name: "Save category" });
  await saveCategory.focus();
  await page.keyboard.press("Enter");
  await expect(tagDialog).not.toBeVisible();
});
