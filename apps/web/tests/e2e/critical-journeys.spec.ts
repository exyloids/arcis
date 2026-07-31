import { expect, test, type Page, type Route } from "@playwright/test";

const account = {
  id: "11111111-1111-4111-8111-111111111111",
  display_name: "Everyday Savings",
  institution_code: "ICICI",
  account_type: "bank_account",
  product_name: "ICICI Savings",
  masked_identifier: "••••1234",
  currency: "INR",
  version: 1,
};
const parentCategory = {
  id: "22222222-2222-4222-8222-222222222222",
  code: "food_drinks",
  name: "Food & Drinks",
  parent_id: null,
  parent_name: null,
  usage_count: 4,
};
const childCategory = {
  id: "33333333-3333-4333-8333-333333333333",
  code: "food_drinks_eating_out",
  name: "Eating Out",
  parent_id: parentCategory.id,
  parent_name: parentCategory.name,
  usage_count: 3,
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
  subcategory: null,
  subcategory_id: null,
};
const mailbox = {
  id: "66666666-6666-4666-8666-666666666666",
  display_email: "owner@example.com",
  connection_status: "connected",
  history_cursor: null,
  last_successful_sync_at: null,
};
const discoveredAccount = {
  id: "77777777-7777-4777-8777-777777777777",
  mailbox_id: mailbox.id,
  mailbox_email: mailbox.display_email,
  institution_code: "icici",
  account_type: "bank_account",
  masked_identifier: "••••1234",
  suggested_product_name: "ICICI Bank Account",
  suggested_display_name: "ICICI Bank Account ••••1234",
  currency: "INR",
  state: "pending",
  financial_account_id: null,
  transaction_alert_count: 2,
  last_detected_at: "2026-07-29T12:00:00Z",
};
const statementNotification = {
  id: "88888888-8888-4888-8888-888888888888",
  notification_kind: "bank_statement_password_required",
  title: "New ICICI bank statement detected",
  body: "Confirm the PDF password to review the latest statement and update the recorded account balance.",
  state: "unread",
  due_at: null,
  action_kind: "confirm_statement_password",
  action_payload: {
    artifact_id: "99999999-9999-4999-8999-999999999999",
    account_id: account.id,
    institution_code: "icici",
    filename: "bank-statement.pdf",
    password_hint: "Use your Customer ID as the PDF password.",
  },
};

function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function mockApi(page: Page) {
  let discoveryState: "pending" | "confirmed" = "pending";
  let accountPresent = true;
  let accountName = account.display_name;
  let notificationUnread = true;
  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (request.method() === "POST" && path.endsWith("/confirm")) {
      discoveryState = "confirmed";
      return json(route, { ...discoveredAccount, state: "confirmed", transactions_imported: 2 });
    }
    if (request.method() === "POST" && path === `/api/v1/statement-attachments/${statementNotification.action_payload.artifact_id}/preview`) {
      return json(route, {
        import: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", filename: "bank-statement.pdf", row_count: 1, valid_row_count: 1, invalid_row_count: 0, state: "preview_ready" },
        rows: [transaction],
        errors: [],
        statement: { parser_name: "icici_bank_v1", period_start: "2026-07-01", period_end: "2026-07-31", opening_balance: "50000", closing_balance: "49150", statement_amount: null, minimum_due: null, due_date: null },
      });
    }
    if (request.method() === "PATCH" && path === `/api/v1/notifications/${statementNotification.id}`) {
      notificationUnread = false;
      return json(route, { ...statementNotification, state: "read" });
    }
    if (request.method() === "PATCH" && path === `/api/v1/financial-accounts/${account.id}`) {
      accountName = String((request.postDataJSON() as { display_name: string }).display_name);
      return json(route, { ...account, display_name: accountName, version: 2 });
    }
    if (request.method() === "PATCH" && path === `/api/v1/transactions/${transaction.id}`) {
      return json(route, {
        ...transaction,
        category_id: parentCategory.id,
        subcategory_id: childCategory.id,
        matching_transaction_count: 2,
        matched_merchant: transaction.merchant_normalized,
      });
    }
    if (request.method() === "POST" && path === `/api/v1/transactions/${transaction.id}/category-matches`) {
      return json(route, { updated: 2, merchant: transaction.merchant_normalized, category_id: parentCategory.id, subcategory_id: childCategory.id });
    }
    if (request.method() === "DELETE" && path === `/api/v1/financial-accounts/${account.id}`) {
      accountPresent = false;
      return route.fulfill({ status: 204, body: "" });
    }
    if (request.method() !== "GET") return json(route, {});
    if (path === "/api/v1/preferences") return json(route, { reporting_period: "this_month" });
    if (path === "/api/v1/financial-accounts") {
      return json(route, accountPresent ? [{ ...account, display_name: accountName }] : []);
    }
    if (path === "/api/v1/mailboxes") return json(route, [mailbox]);
    if (path === "/api/v1/notifications") {
      return json(route, notificationUnread ? [statementNotification] : []);
    }
    if (path === "/api/v1/discovered-accounts") {
      return json(route, [{ ...discoveredAccount, state: discoveryState }]);
    }
    if (path === "/api/v1/categories") return json(route, [parentCategory, childCategory]);
    if (path === `/api/v1/transactions/${transaction.id}/category-matches`) {
      return json(route, {
        transaction_id: transaction.id,
        merchant: transaction.merchant_normalized,
        category_id: parentCategory.id,
        subcategory_id: childCategory.id,
        matching_transaction_count: 2,
      });
    }
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
        cash_balance_complete: true,
        unavailable_bank_balances: 0,
        credit_card_outstanding: "0",
        net_worth: "49150.00",
        accounts: accountPresent ? [{
          ...account,
          display_name: accountName,
          balance: "49150.00",
          balance_source: "statement_plus_transactions",
          balance_as_of: "2026-07-28",
          calculated_change: "-850.00",
          currency: "INR",
        }] : [],
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
          percentage: "85.0",
        }, {
          category_id: null,
          category: "Uncategorized",
          amount: "150.00",
          percentage: "15.0",
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
  await page.locator(".spending-category-list article").filter({ hasText: "Uncategorized" }).getByRole("button", { name: "Show transactions →" }).click();
  await expect(page.getByRole("heading", { name: "Transactions", level: 1 })).toBeVisible();
  await page.getByRole("button", { name: "Filter transactions" }).click();
  await expect(page.getByLabel("Category")).toHaveValue("__uncategorized__");
  await expect(page.getByRole("button", { name: "Clear filters" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await page.getByRole("button", { name: "Filter transactions" }).click();
  await expect(page.getByLabel("Category")).toHaveValue("");

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
  const categorySearch = tagDialog.getByRole("textbox", { name: "Search categories or subcategories" });
  await categorySearch.fill("Eating");
  await expect(tagDialog.getByRole("button", { name: /Eating Out/ })).toBeVisible();
  await categorySearch.clear();
  await expect(tagDialog.getByText("Frequently used")).toBeVisible();
  await tagDialog.getByRole("button", { name: /Eating Out/ }).click();
  await expect(tagDialog.locator(".tag-group.selected").getByRole("button", { name: /Food & Drinks/ })).toBeVisible();
  await expect(tagDialog.getByRole("button", { name: /Eating Out/ })).toHaveClass(/selected/);
  const saveCategory = tagDialog.getByRole("button", { name: "Save category" });
  await saveCategory.focus();
  await page.keyboard.press("Enter");
  await expect(tagDialog).not.toBeVisible();
  const matchDialog = page.getByRole("dialog", { name: "Tag 2 more transactions?" });
  await expect(matchDialog.getByText("Demo Cafe")).toBeVisible();
  await matchDialog.getByRole("button", { name: "Tag 2 transactions" }).click();
  await expect(page.getByText("2 matching transactions tagged.")).toBeVisible();
});

test("detected Gmail account remains gated until confirmation", async ({ page }) => {
  await page.getByRole("button", { name: "Mailboxes" }).first().click();
  await expect(page.getByRole("heading", { name: "Mailboxes", exact: true })).toHaveCount(1);
  await expect(page.getByText("GMAIL", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Statement attachments" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Unsupported email review" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Detected accounts and cards" })).toBeVisible();
  await expect(page.getByText("ICICI ••••1234")).toBeVisible();
  await expect(page.getByText("Nothing enters your accounts")).toBeVisible();

  await page.getByRole("button", { name: "Confirm & add" }).click();
  await expect(page.getByText("Account added. 2 detected transaction(s) imported.")).toBeVisible();
  await expect(page.getByText("No products waiting for confirmation")).toBeVisible();
  await page.getByText("Reviewed products (1)").click();
  await expect(page.getByText("Added to Arcis")).toBeVisible();
});

test("confirmed account details can be edited and the account can be removed", async ({ page }) => {
  await page.getByRole("button", { name: "Accounts" }).first().click();
  await page.getByRole("button", { name: "Edit" }).click();

  const editor = page.getByRole("dialog", { name: "EDIT ACCOUNT" });
  await expect(editor).toBeVisible();
  await editor.getByLabel("Display name").fill("Salary Savings");
  await editor.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Account details updated.")).toBeVisible();
  await expect(page.getByText("Salary Savings")).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Remove" }).click();
  await expect(page.getByText("No confirmed bank accounts yet.")).toBeVisible();
});

test("statement notification requests an ephemeral password and opens a preview", async ({ page }) => {
  await page.getByRole("button", { name: /Open notifications/ }).click();
  await expect(page.getByRole("heading", { name: "Notifications", level: 1 })).toBeVisible();
  await expect(page.getByText("New ICICI bank statement detected")).toBeVisible();
  await page.getByRole("button", { name: "Review" }).click();

  const dialog = page.getByRole("dialog", { name: "CONFIRM STATEMENT" });
  await expect(dialog.getByText("Use your Customer ID as the PDF password.")).toBeVisible();
  await expect(dialog.getByLabel("Savings account")).toHaveValue(account.id);
  await dialog.getByLabel("PDF password").fill("ephemeral-test-password");
  await dialog.getByRole("button", { name: "Open statement preview" }).click();

  await expect(page.getByRole("heading", { name: "Imports", level: 1 })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Import preview · bank-statement.pdf" })).toBeVisible();
  await expect(page.getByText("Statement opened. Review and confirm it to update the recorded balance.")).toBeVisible();
});
