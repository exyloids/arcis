"use client";

import { ChangeEvent, FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Apple, Armchair, BatteryCharging, Beef, Bell, Bike, BookOpen, Briefcase, Building2, BusFront, Cake, CalendarDays, Car, CircleDollarSign, Coffee, CreditCard, Droplets, Dumbbell, Flame, Footprints, Fuel, Gamepad2, Gem, Gift, HeartPulse, House, Landmark, Milk, Monitor, MoreHorizontal, Music2, Package, ParkingCircle, PartyPopper, PenLine, Phone, Pill, Pizza, Plane, RefreshCw, Scissors, ShieldCheck, Shirt, ShoppingBasket, Sparkles, Sprout, Stethoscope, TestTube, Ticket, ToyBrick, TrainFront, Truck, Trophy, Tv, Users, Utensils, Wifi, Wine, Wrench, Zap, type LucideIcon } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const navigation = [
  ["home", "Home"], ["transactions", "Transactions"], ["spending", "Spending"], ["budgets", "Budgets"], ["recurring", "Recurring"], ["accounts", "Accounts"],
  ["cards", "Cards"], ["imports", "Imports"], ["notifications", "Notifications"], ["mailboxes", "Mailboxes"], ["privacy", "Privacy"],
] as const;

type View = (typeof navigation)[number][0];
type Account = { id: string; display_name: string; institution_code: string; account_type: string; product_name: string; masked_identifier: string | null; currency: string; version: number };
type AccountBalance = Account & { balance: string | null; currency: string; balance_source: "statement_plus_transactions" | "transactions" | "unavailable"; balance_as_of: string | null; calculated_change: string };
type Transaction = { id: string; transaction_date: string; narration: string; merchant_normalized?: string | null; provider_reference?: string | null; amount: string; currency: string; direction: string; account_name: string; category: string | null; category_id: string | null; subcategory: string | null; subcategory_id: string | null };
type CategoryMatchPreview = { transaction_id: string; merchant: string; category_id: string | null; subcategory_id: string | null; matching_transaction_count: number };
type CategoryMatchPrompt = { transactionId: string; merchant: string; category: string; count: number };
type Category = { id: string; code: string; name: string; parent_id?: string | null; parent_name?: string | null; usage_count?: number };
type TransactionPage = { items: Transaction[]; next_cursor: string | null };
type Preview = { import: { id: string; filename: string; row_count: number; valid_row_count: number; invalid_row_count: number; state: string }; rows: Transaction[]; errors: Array<{ ordinal: number; message: string }>; statement?: { parser_name: string; period_start: string | null; period_end: string | null; opening_balance: string | null; closing_balance: string | null; statement_amount: string | null; minimum_due: string | null; due_date: string | null } };
type Report = { income: string; expense: string; categories: Array<{ category: string; direction: string; amount: string }> };
type BalanceSummary = { cash_balance: string; cash_balance_complete: boolean; unavailable_bank_balances: number; credit_card_outstanding: string; net_worth: string; accounts: AccountBalance[] };
type ImportItem = { id: string; filename: string; state: string; row_count: number; valid_row_count: number; invalid_row_count: number; duplicate_count: number; created_at: string; confirmed_at: string | null };
type Inspection = { headers: string[]; suggested_mapping: Record<string, string>; sample_row_count: number };
type Mapping = Record<string, string>;
type Mailbox = { id: string; display_email: string; connection_status: string; history_cursor: string | null; last_successful_sync_at: string | null };
type DiscoveredAccount = { id: string; mailbox_id: string; mailbox_email: string | null; institution_code: string; account_type: "bank_account" | "credit_card"; masked_identifier: string; suggested_product_name: string; suggested_display_name: string; currency: string; state: "pending" | "confirmed" | "rejected"; financial_account_id: string | null; transaction_alert_count: number; last_detected_at: string };
type ReconciliationReview = { id: string; state: string; match_method: string; match_score: string; reason: string; ordinal: number; transaction_date: string; narration: string; amount: string; direction: string; candidate_narration: string | null; candidate_date: string | null };
type RecurringPayment = { id: string; display_name: string; account_name: string; category: string | null; cadence: string; typical_amount: string; monthly_equivalent: string; next_expected_on: string; confidence: string; kind: "recurring" | "subscription"; occurrence_count: number; state: "detected" | "confirmed" | "dismissed" };
type MonthlyInsights = { month: string; expense: string; forecast: { projected_expense: string; days_observed: number; days_in_month: number } | null; anomalies: Array<{ kind: string; title: string; amount: string; category?: string; merchant?: string; reason: string }> };
type SpendingSummary = { expense: string; categories: Array<{ category_id: string | null; category: string; amount: string; percentage: string }> };
type SpendingTrend = { category_id: string; granularity: "monthly" | "yearly"; points: Array<{ period: string; amount: string }> };
type Budget = { id: string; category_id: string; category: string; monthly_limit: string; active: boolean; spent: string; remaining: string; percentage: string; over_budget: boolean };
type CardStatement = { id: string; account_name: string; period_end: string | null; statement_amount: string | null; minimum_due: string | null; due_date: string | null; payment_status: "unpaid" | "partial" | "paid"; paid_amount: string };
type NotificationItem = { id: string; notification_kind: string; title: string; body: string; state: "unread" | "read" | "dismissed"; due_at: string | null; action_kind: string | null; action_payload: { artifact_id?: string; account_id?: string | null; institution_code?: string; filename?: string; password_hint?: string } };
type PrivacyInventory = { accounts: number; transactions: number; stored_documents: number; connected_mailboxes: number; retention_policy: { source_artifacts_days: number; statement_files_days: number } };
type ReportingPeriod = "all_time" | "this_month" | "last_month" | "last_3_months" | "last_6_months" | "this_year";

const reportingPeriods: Array<[ReportingPeriod, string]> = [
  ["all_time", "All time"], ["this_month", "This month"], ["last_month", "Last month"],
  ["last_3_months", "Last 3 months"], ["last_6_months", "Last 6 months"], ["this_year", "This year"],
];

const mappingFields: Array<[keyof Mapping, string, boolean]> = [
  ["transaction_date", "Transaction date", true], ["posted_date", "Posted date", false],
  ["narration", "Narration", true], ["debit", "Debit amount", true],
  ["credit", "Credit amount", true], ["provider_reference", "Reference", false],
];

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, cache: "no-store" });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(problem.detail ?? "Request failed");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export default function HomePage() {
  const [activeView, setActiveView] = useState<View>("home");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [editingAccount, setEditingAccount] = useState<Account | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [balanceSummary, setBalanceSummary] = useState<BalanceSummary | null>(null);
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pdfPassword, setPdfPassword] = useState("");
  const [message, setMessage] = useState("");
  const [ledgerAccountId, setLedgerAccountId] = useState("");
  const [ledgerCategoryId, setLedgerCategoryId] = useState("");
  const [ledgerUncategorized, setLedgerUncategorized] = useState(false);
  const [reportingPeriod, setReportingPeriod] = useState<ReportingPeriod>("this_month");
  const [ledgerAccountType, setLedgerAccountType] = useState<"bank_account" | "credit_card">("bank_account");
  const [search, setSearch] = useState("");
  const [showLedgerFilters, setShowLedgerFilters] = useState(false);
  const [showPeriodPicker, setShowPeriodPicker] = useState(false);
  const [evidence, setEvidence] = useState<Array<Record<string, string>> | null>(null);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [showTransactionMoreDetails, setShowTransactionMoreDetails] = useState(false);
  const [taggingTransaction, setTaggingTransaction] = useState<Transaction | null>(null);
  const [tagCategoryId, setTagCategoryId] = useState("");
  const [tagSubcategoryId, setTagSubcategoryId] = useState("");
  const [categoryMatchPrompt, setCategoryMatchPrompt] = useState<CategoryMatchPrompt | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [discoveredAccounts, setDiscoveredAccounts] = useState<DiscoveredAccount[]>([]);
  const [reconciliationReviews, setReconciliationReviews] = useState<ReconciliationReview[]>([]);
  const [recurringPayments, setRecurringPayments] = useState<RecurringPayment[]>([]);
  const [monthlyInsights, setMonthlyInsights] = useState<MonthlyInsights | null>(null);
  const [spendingSummary, setSpendingSummary] = useState<SpendingSummary | null>(null);
  const [selectedSpendingCategoryId, setSelectedSpendingCategoryId] = useState("");
  const [spendingTrend, setSpendingTrend] = useState<SpendingTrend | null>(null);
  const [spendingGranularity, setSpendingGranularity] = useState<"monthly" | "yearly">("monthly");
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [cardStatements, setCardStatements] = useState<CardStatement[]>([]);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [statementNotification, setStatementNotification] = useState<NotificationItem | null>(null);
  const [privacyInventory, setPrivacyInventory] = useState<PrivacyInventory | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const dialogReturnFocus = useRef<HTMLElement | null>(null);
  const [backfillMailboxId, setBackfillMailboxId] = useState("");
  const [backfillQuery, setBackfillQuery] = useState("from:(alerts@alerts.icicibank.com OR alerts@alerts.hdfcbank.com) newer_than:365d");
  const currentMonth = new Date().toISOString().slice(0, 7);
  const bankAccounts = balanceSummary?.accounts.filter((account) => account.account_type === "bank_account") ?? [];
  const creditCards = balanceSummary?.accounts.filter((account) => account.account_type === "credit_card") ?? [];
  const bankAccountDetails = accounts.filter((account) => account.account_type === "bank_account");
  const creditCardDetails = accounts.filter((account) => account.account_type === "credit_card");

  async function loadLedger() {
    const ledgerParams = new URLSearchParams();
    ledgerParams.set("period", reportingPeriod);
    ledgerParams.set("account_type", ledgerAccountType);
    if (ledgerAccountId) ledgerParams.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) ledgerParams.set("category_id", ledgerCategoryId);
    if (ledgerUncategorized) ledgerParams.set("uncategorized", "true");
    if (search.trim()) ledgerParams.set("q", search.trim());
    const page = await request<TransactionPage>(`/api/v1/transactions/page?${ledgerParams}`);
    setTransactions(page.items); setNextCursor(page.next_cursor);
  }

  async function refresh(selectedPeriod: ReportingPeriod = reportingPeriod) {
    const ledgerParams = new URLSearchParams();
    ledgerParams.set("period", selectedPeriod);
    ledgerParams.set("account_type", ledgerAccountType);
    if (ledgerAccountId) ledgerParams.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) ledgerParams.set("category_id", ledgerCategoryId);
    if (ledgerUncategorized) ledgerParams.set("uncategorized", "true");
    if (search.trim()) ledgerParams.set("q", search.trim());
    const [nextAccounts, nextCategories, transactionPage, nextReport, nextBalanceSummary, nextImports, nextMailboxes, nextDiscoveredAccounts, nextReviews, nextRecurringPayments, nextMonthlyInsights, nextSpendingSummary, nextBudgets, nextCardStatements, nextNotifications, nextPrivacyInventory] = await Promise.all([
      request<Account[]>("/api/v1/financial-accounts"), request<Category[]>("/api/v1/categories"),
      request<TransactionPage>(`/api/v1/transactions/page?${ledgerParams}`), request<Report>(`/api/v1/reports/period?period=${selectedPeriod}`),
      request<BalanceSummary>("/api/v1/accounts/balance-summary"), request<ImportItem[]>("/api/v1/imports"),
      request<Mailbox[]>("/api/v1/mailboxes"),
      request<DiscoveredAccount[]>("/api/v1/discovered-accounts"),
      request<ReconciliationReview[]>("/api/v1/reconciliation-reviews"),
      request<RecurringPayment[]>("/api/v1/recurring-payments"),
      request<MonthlyInsights>(`/api/v1/insights/monthly?month=${currentMonth}`),
      request<SpendingSummary>("/api/v1/spending/summary"),
      request<Budget[]>(`/api/v1/budgets?month=${currentMonth}`),
      request<CardStatement[]>("/api/v1/card-statements"),
      request<NotificationItem[]>("/api/v1/notifications?state=unread"),
      request<PrivacyInventory>("/api/v1/privacy/inventory"),
    ]);
    setAccounts(nextAccounts); setCategories(nextCategories); setTransactions(transactionPage.items); setNextCursor(transactionPage.next_cursor);
    setReport(nextReport); setBalanceSummary(nextBalanceSummary); setImports(nextImports); setMailboxes(nextMailboxes);
    setDiscoveredAccounts(nextDiscoveredAccounts); setReconciliationReviews(nextReviews);
    setRecurringPayments(nextRecurringPayments);
    setMonthlyInsights(nextMonthlyInsights);
    setSpendingSummary(nextSpendingSummary);
    setBudgets(nextBudgets);
    setCardStatements(nextCardStatements); setNotifications(nextNotifications);
    setPrivacyInventory(nextPrivacyInventory);
    setSelectedSpendingCategoryId((current) => current || nextSpendingSummary.categories[0]?.category_id || "");
    if (!accountId && nextAccounts[0]) setAccountId(nextAccounts[0].id);
    if (!backfillMailboxId && nextMailboxes[0]) setBackfillMailboxId(nextMailboxes[0].id);
  }

  useEffect(() => {
    void request<{ reporting_period: ReportingPeriod }>("/api/v1/preferences")
      .then(async (preferences) => { setReportingPeriod(preferences.reporting_period); await refresh(preferences.reporting_period); })
      .catch((error: Error) => setMessage(error.message)).finally(() => setHasLoaded(true));
  }, []);
  useEffect(() => {
    if (activeView !== "transactions") return;
    const timer = window.setTimeout(() => { void loadLedger().catch((error: Error) => setMessage(error.message)); }, 160);
    return () => window.clearTimeout(timer);
  }, [activeView, ledgerAccountType, ledgerAccountId, ledgerCategoryId, ledgerUncategorized, reportingPeriod, search]);
  useEffect(() => {
    if (activeView !== "spending" || !selectedSpendingCategoryId) return;
    void request<SpendingTrend>(`/api/v1/spending/categories/${selectedSpendingCategoryId}/trend?granularity=${spendingGranularity}`)
      .then(setSpendingTrend).catch((error: Error) => setMessage(error.message));
  }, [activeView, selectedSpendingCategoryId, spendingGranularity]);
  useEffect(() => {
    if (!selectedTransaction && !taggingTransaction && !categoryMatchPrompt && !evidence && !statementNotification) return;
    if (!dialogReturnFocus.current && document.activeElement instanceof HTMLElement) {
      dialogReturnFocus.current = document.activeElement;
    }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleDialogKeyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (statementNotification) setStatementNotification(null);
        else if (taggingTransaction) setTaggingTransaction(null);
        else if (categoryMatchPrompt) setCategoryMatchPrompt(null);
        else if (evidence) setEvidence(null);
        else setSelectedTransaction(null);
        return;
      }
      if (event.key !== "Tab") return;
      const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"]');
      const dialog = dialogs.item(dialogs.length - 1);
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleDialogKeyboard);
    return () => {
      window.removeEventListener("keydown", handleDialogKeyboard);
      document.body.style.overflow = previousOverflow;
    };
  }, [selectedTransaction, taggingTransaction, categoryMatchPrompt, evidence, statementNotification]);
  useEffect(() => {
    if (selectedTransaction || taggingTransaction || categoryMatchPrompt || evidence || statementNotification || !dialogReturnFocus.current) return;
    dialogReturnFocus.current.focus();
    dialogReturnFocus.current = null;
  }, [selectedTransaction, taggingTransaction, categoryMatchPrompt, evidence, statementNotification]);

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const formElement = event.currentTarget;
    try { await request("/api/v1/financial-accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(formElement))) }); formElement.reset(); setMessage("Account created."); await refresh(); }
    catch (error) { setMessage((error as Error).message); }
  }

  async function updateAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingAccount) return;
    const form = event.currentTarget;
    try {
      await request(`/api/v1/financial-accounts/${editingAccount.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      setEditingAccount(null);
      setMessage("Account details updated.");
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }

  async function removeAccount(account: Account) {
    const kind = account.account_type === "credit_card" ? "card" : "account";
    if (!window.confirm(`Remove ${account.display_name} from active ${kind}s? Existing transaction history will be retained, and future Gmail alerts for this product will be skipped.`)) return;
    try {
      await request(`/api/v1/financial-accounts/${account.id}`, { method: "DELETE" });
      if (editingAccount?.id === account.id) setEditingAccount(null);
      setMessage(`${account.display_name} removed from active ${kind}s.`);
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function inspectFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!accountId || !file) return setMessage("Select an account and CSV/XLSX statement.");
    if (file.name.toLowerCase().endsWith(".pdf")) return void createPreview();
    const body = new FormData(); body.append("file", file);
    try { const result = await request<Inspection>("/api/v1/imports/inspect", { method: "POST", body }); setInspection(result); setMapping(result.suggested_mapping); setMessage(`Found ${result.sample_row_count} rows. Review the column mapping before creating a preview.`); }
    catch (error) { setMessage((error as Error).message); }
  }
  async function createPreview() {
    if (!accountId || !file) return; const isPdf = file.name.toLowerCase().endsWith(".pdf");
    const missing = mappingFields.filter(([field, , required]) => required && !mapping[field]);
    if (!isPdf && missing.length) return setMessage(`Map required columns: ${missing.map(([, label]) => label).join(", ")}.`);
    const body = new FormData(); body.append("file", file);
    if (isPdf) body.append("pdf_password", pdfPassword); else body.append("column_mapping", JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([, value]) => value))));
    try { const result = await request<Preview>(`/api/v1/imports?account_id=${accountId}`, { method: "POST", body }); setPreview(result); setInspection(null); setPdfPassword(""); setMessage("Review the parsed rows before confirmation."); }
    catch (error) { setMessage((error as Error).message); }
  }
  async function confirmStatementNotification(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!statementNotification?.action_payload.artifact_id || !accountId) return;
    try {
      const result = await request<Preview>(
        `/api/v1/statement-attachments/${statementNotification.action_payload.artifact_id}/preview?account_id=${accountId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ pdf_password: pdfPassword }),
        },
      );
      await request(`/api/v1/notifications/${statementNotification.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: "read" }),
      });
      setPreview(result);
      setPdfPassword("");
      setStatementNotification(null);
      setActiveView("imports");
      setMessage("Statement opened. Review and confirm it to update the recorded balance.");
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  function openNotificationAction(notification: NotificationItem) {
    if (notification.action_kind !== "confirm_statement_password") return;
    setStatementNotification(notification);
    setAccountId(notification.action_payload.account_id ?? "");
    setPdfPassword("");
  }
  async function confirmImport() {
    if (!preview) return;
    try { const result = await request<{ created: number; duplicates?: number; matched?: number; uncertain?: number; categorized?: number }>(`/api/v1/imports/${preview.import.id}/confirm`, { method: "POST" }); const categorization = result.categorized ? ` ${result.categorized} transaction(s) categorized.` : ""; setMessage(preview.statement ? `Statement confirmed: ${result.created} statement-only transactions, ${result.matched ?? 0} matched, ${result.uncertain ?? 0} need review.${categorization}` : `Import confirmed: ${result.created} transactions created, ${result.duplicates ?? 0} duplicates ignored.${categorization}`); setPreview(null); setFile(null); await refresh(); }
    catch (error) { setMessage((error as Error).message); }
  }
  async function cancelImport(importId: string) { try { await request<void>(`/api/v1/imports/${importId}/cancel`, { method: "POST" }); if (preview?.import.id === importId) setPreview(null); setMessage("Import cancelled and its staged document removed."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function openImport(importId: string) { try { setPreview(await request<Preview>(`/api/v1/imports/${importId}/preview`)); setActiveView("imports"); setMessage("Viewing stored import preview."); } catch (error) { setMessage((error as Error).message); } }
  async function saveTaggedCategory() {
    if (!taggingTransaction || !tagCategoryId) return;
    const transaction = taggingTransaction;
    const category = categories.find((item) => item.id === tagCategoryId);
    try {
      await request<Transaction>(`/api/v1/transactions/${transaction.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category_id: tagCategoryId,
          subcategory_id: tagSubcategoryId || null,
          remember_merchant: true,
        }),
      });
      const matches = await request<CategoryMatchPreview>(
        `/api/v1/transactions/${transaction.id}/category-matches`,
      );
      setTaggingTransaction(null);
      setSelectedTransaction(null);
      if (matches.matching_transaction_count > 0) {
        setCategoryMatchPrompt({
          transactionId: transaction.id,
          merchant: matches.merchant,
          category: category?.parent_name ?? category?.name ?? "the selected category",
          count: matches.matching_transaction_count,
        });
        setMessage("Category saved. Future transactions from this vendor will be tagged automatically.");
      } else {
        setMessage("Category saved and remembered for future transactions from this vendor.");
      }
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function applyCategoryToMatches() {
    if (!categoryMatchPrompt) return;
    try {
      const result = await request<{ updated: number }>(
        `/api/v1/transactions/${categoryMatchPrompt.transactionId}/category-matches`,
        { method: "POST" },
      );
      setCategoryMatchPrompt(null);
      setMessage(`${result.updated} matching transaction${result.updated === 1 ? "" : "s"} tagged. Future transactions from this vendor will also be tagged automatically.`);
      await refresh();
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  async function showEvidence(transactionId: string) { try { setEvidence(await request<Array<Record<string, string>>>(`/api/v1/transactions/${transactionId}/evidence`)); } catch (error) { setMessage((error as Error).message); } }
  async function categorizeTransactions() { try { const result = await request<{ rules: number; transactions_updated: number }>("/api/v1/categories/categorize", { method: "POST" }); setMessage(`${result.transactions_updated} transactions categorized using ${result.rules} deterministic rules.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function loadMore() { if (!nextCursor) return; const params = new URLSearchParams({ cursor: nextCursor, period: reportingPeriod }); params.set("account_type", ledgerAccountType); if (ledgerAccountId) params.set("account_id", ledgerAccountId); if (ledgerCategoryId) params.set("category_id", ledgerCategoryId); if (ledgerUncategorized) params.set("uncategorized", "true"); if (search.trim()) params.set("q", search.trim()); try { const page = await request<TransactionPage>(`/api/v1/transactions/page?${params}`); setTransactions([...transactions, ...page.items]); setNextCursor(page.next_cursor); } catch (error) { setMessage((error as Error).message); } }
  async function changeReportingPeriod(period: ReportingPeriod) { const previous = reportingPeriod; setReportingPeriod(period); setShowPeriodPicker(false); try { await request("/api/v1/preferences/reporting-period", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reporting_period: period }) }); await refresh(period); } catch (error) { setReportingPeriod(previous); setMessage((error as Error).message); } }
  async function createBudget(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; try { await request("/api/v1/budgets", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) }); form.reset(); setMessage("Monthly budget saved."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function removeBudget(id: string) { try { await request<void>(`/api/v1/budgets/${id}`, { method: "DELETE" }); setMessage("Budget removed."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function generateCardReminders() { try { const result = await request<{ created: number }>("/api/v1/card-statements/reminders/generate", { method: "POST" }); setMessage(`${result.created} new card reminder(s) created.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function markStatementPaid(id: string, amount: string | null) { try { await request(`/api/v1/card-statements/${id}/payment`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "paid", paid_amount: amount ?? "0" }) }); setMessage("Card statement marked paid."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function dismissNotification(id: string) { try { await request(`/api/v1/notifications/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state: "dismissed" }) }); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function downloadPrivacyExport() { try { const data = await request<Record<string, unknown>>("/api/v1/privacy/export"); const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `arcis-export-${new Date().toISOString().slice(0, 10)}.json`; anchor.click(); URL.revokeObjectURL(url); setMessage("Your privacy export was downloaded."); } catch (error) { setMessage((error as Error).message); } }
  async function updateRetention(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = event.currentTarget; try { await request("/api/v1/privacy/retention", { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) }); setMessage("Retention settings updated."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function enforceRetention() { if (!window.confirm("Apply the retention policy now? Expired raw source files will enter a 30-day recovery window.")) return; try { const result = await request<{ redacted: number; purged: number }>("/api/v1/privacy/retention/enforce", { method: "POST" }); setMessage(`Retention complete: ${result.redacted} file(s) moved to recovery and ${result.purged} expired recovery file(s) purged.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function syncMailbox(mailboxId: string) { try { const job = await request<{ id: string }>(`/api/v1/mailboxes/${mailboxId}/sync`, { method: "POST" }); setMessage(`Sync queued: ${job.id}`); } catch (error) { setMessage((error as Error).message); } }
  async function waitForSyncJob(jobId: string) { for (let attempt = 0; attempt < 240; attempt += 1) { const job = await request<{ state: string; error_code: string | null; progress: Record<string, number | string> }>(`/api/v1/sync-jobs/${jobId}`); if (job.state === "completed") return job; if (job.state === "failed") throw new Error(job.error_code === "gmail_reconnect_required" ? "Reconnect Gmail and try again." : "Gmail scan failed. Check the worker logs and try again."); await new Promise((resolve) => window.setTimeout(resolve, 1000)); } throw new Error("The Gmail scan is still running. Refresh this page in a moment to see detected products."); }
  async function syncConnectedMailboxes() {
    if (isSyncing) return;
    const connected = mailboxes.filter((mailbox) => mailbox.connection_status === "connected");
    if (!connected.length) {
      setMessage("Connect Gmail before refreshing transactions and statements.");
      return;
    }
    setIsSyncing(true);
    setMessage(`Checking ${connected.length} connected mailbox${connected.length === 1 ? "" : "es"} for new transactions and statements…`);
    try {
      const queued = await Promise.all(
        connected.map((mailbox) => request<{ id: string }>(`/api/v1/mailboxes/${mailbox.id}/sync`, { method: "POST" })),
      );
      const results = await Promise.allSettled(queued.map((job) => waitForSyncJob(job.id)));
      const completed = results.filter((result) => result.status === "fulfilled");
      const failed = results.length - completed.length;
      const totals = completed.reduce(
        (summary, result) => {
          if (result.status !== "fulfilled") return summary;
          summary.scanned += Number(result.value.progress.scanned ?? 0);
          summary.added += Number(result.value.progress.added ?? 0);
          return summary;
        },
        { scanned: 0, added: 0 },
      );
      await refresh();
      setMessage(
        failed
          ? `Refresh finished with ${failed} failed mailbox sync${failed === 1 ? "" : "s"}. ${totals.scanned} emails checked and ${totals.added} new emails added.`
          : `Refresh complete: ${totals.scanned} emails checked and ${totals.added} new emails added.`,
      );
    } catch (error) {
      setMessage((error as Error).message);
      await refresh().catch(() => undefined);
    } finally {
      setIsSyncing(false);
    }
  }
  async function discoverMailboxAccounts(mailboxId: string) { try { setMessage("Gmail account scan queued…"); const queued = await request<{ id: string }>(`/api/v1/mailboxes/${mailboxId}/discover-accounts`, { method: "POST" }); const job = await waitForSyncJob(queued.id); setMessage(`Scan complete: ${job.progress.scanned ?? 0} emails checked, ${job.progress.products_detected ?? 0} products detected, ${job.progress.new_products ?? 0} new.`); await refresh(); } catch (error) { setMessage((error as Error).message); await refresh(); } }
  async function confirmDiscoveredAccount(event: FormEvent<HTMLFormElement>, id: string) { event.preventDefault(); const form = event.currentTarget; try { const result = await request<{ transactions_imported: number }>(`/api/v1/discovered-accounts/${id}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) }); setMessage(`Account added. ${result.transactions_imported} detected transaction(s) imported.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function rejectDiscoveredAccount(id: string) { if (!window.confirm("Ignore this account or card? Its current and future detected transactions will be skipped.")) return; try { await request(`/api/v1/discovered-accounts/${id}/reject`, { method: "POST" }); setMessage("Account ignored. Future matching transactions will be skipped."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function reconsiderDiscoveredAccount(id: string) { try { await request(`/api/v1/discovered-accounts/${id}/reconsider`, { method: "POST" }); setMessage("Account is available for review again."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function disconnectMailbox(mailboxId: string) { if (!window.confirm("Disconnect this Gmail mailbox? Existing ledger data will remain.")) return; try { await request<void>(`/api/v1/mailboxes/${mailboxId}/disconnect`, { method: "POST" }); setMessage("Gmail mailbox disconnected and its credential revoked."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function backfillMailbox(event: FormEvent<HTMLFormElement>) { event.preventDefault(); try { const result = await request<{ scanned: number; added: number; duplicates: number }>(`/api/v1/mailboxes/${backfillMailboxId}/backfill`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: backfillQuery, max_results: 500 }) }); setMessage(`Backfill complete: ${result.scanned} scanned, ${result.added} added, ${result.duplicates} duplicates.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function resolveReconciliation(reviewId: string, state: "accepted" | "rejected") { try { await request(`/api/v1/reconciliation-reviews/${reviewId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state }) }); setMessage(`Reconciliation ${state}.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function detectRecurringPayments() { try { const result = await request<{ detected: number }>("/api/v1/recurring-payments/detect", { method: "POST" }); setMessage(`${result.detected} recurring payment pattern(s) found for review.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function reviewRecurringPayment(id: string, state: "detected" | "confirmed" | "dismissed") { try { await request(`/api/v1/recurring-payments/${id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state }) }); setMessage(`Recurring payment ${state}.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function updateRecurringPayment(id: string, payload: { display_name: string; typical_amount: string; next_expected_on: string }) { try { await request(`/api/v1/recurring-payments/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); setMessage("Recurring payment details updated."); await refresh(); } catch (error) { setMessage((error as Error).message); throw error; } }
  function openTransactions(type: "bank_account" | "credit_card", selectedAccountId = "") {
    setLedgerAccountType(type);
    setLedgerAccountId(selectedAccountId);
    setLedgerCategoryId("");
    setLedgerUncategorized(false);
    setSearch("");
    setActiveView("transactions");
  }
  function openCategoryTransactions(categoryId: string | null) {
    setLedgerAccountType("bank_account");
    setLedgerAccountId("");
    setLedgerCategoryId(categoryId ?? "");
    setLedgerUncategorized(categoryId === null);
    setSearch("");
    setReportingPeriod("all_time");
    setActiveView("transactions");
  }
  function clearLedgerFilters() {
    setLedgerAccountId("");
    setLedgerCategoryId("");
    setLedgerUncategorized(false);
    setSearch("");
    setShowLedgerFilters(false);
    if (reportingPeriod !== "all_time") void changeReportingPeriod("all_time");
  }
  function openTransactionDetails(transaction: Transaction) { setSelectedTransaction(transaction); setShowTransactionMoreDetails(false); }

  return <main className="app-shell">
    <aside className="sidebar"><button className="brand" onClick={() => setActiveView("home")} aria-label="Go to home"><span>₹</span>Arcis</button><nav>{navigation.map(([view, label]) => <button key={view} className={activeView === view ? "nav-item active" : "nav-item"} onClick={() => setActiveView(view)}>{navIcon(view)}<span>{label}</span></button>)}</nav><div className="sidebar-note"><span className="status-dot" />Private ledger<br /><small>Read-only financial tracking</small></div></aside>
    <div className="main-content">
      <header className="topbar"><div><p className="eyebrow">ARCIS FINANCE</p><h1>{activeView === "home" ? greeting() : viewTitle(activeView)}</h1><p className="subtitle">{activeView === "home" ? "Your money, clearly organised." : viewSubtitle(activeView)}</p></div><div className="top-actions">{activeView === "home" && <select className="global-period" value={reportingPeriod} onChange={(event) => void changeReportingPeriod(event.target.value as ReportingPeriod)} aria-label="Reporting period">{reportingPeriods.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>}<button className="icon-button notification-button" onClick={() => setActiveView("notifications")} aria-label={`Open notifications (${notifications.length} unread)`}><Bell size={19} aria-hidden="true" />{notifications.length > 0 && <b>{notifications.length}</b>}</button><button className={`icon-button refresh-button${isSyncing ? " syncing" : ""}`} onClick={() => void syncConnectedMailboxes()} aria-label={isSyncing ? "Syncing Gmail" : "Sync Gmail and refresh data"} title={isSyncing ? "Syncing Gmail…" : "Get latest transactions and statements"} disabled={isSyncing}><RefreshCw size={19} aria-hidden="true" /></button><button className="profile" onClick={() => setActiveView("mailboxes")} aria-label="Open mailbox settings">A</button></div></header>
      <nav className="mobile-nav" aria-label="Primary navigation">{navigation.map(([view, label]) => <button key={view} className={activeView === view ? "active" : ""} onClick={() => setActiveView(view)}>{navIcon(view)}<span>{label}</span></button>)}</nav>
      {message && <p className="notice" role="status">{message}</p>}

      {activeView === "home" && (hasLoaded ? <>
        <section className="hero-balance"><div><span className="section-kicker">{balanceSummary?.cash_balance_complete ? "Total bank balance" : "Confirmed bank balance"}</span><strong>{formatAmount(balanceSummary?.cash_balance)}</strong><p>{balanceSummary?.cash_balance_complete ? "Savings accounts only · cards tracked separately" : `${balanceSummary?.unavailable_bank_balances ?? 0} account balance${balanceSummary?.unavailable_bank_balances === 1 ? "" : "s"} unavailable until a recent statement is confirmed`}</p></div><button className="text-action" onClick={() => openTransactions("bank_account")}>View transactions →</button></section>
        <section className="summary-grid"><SummaryCard icon="↗" label={`Incoming · ${reportingPeriodLabel(reportingPeriod)}`} value={formatAmount(report?.income)} tone="positive" /><SummaryCard icon="↘" label={`Outgoing · ${reportingPeriodLabel(reportingPeriod)}`} value={formatAmount(report?.expense)} tone="negative" /><SummaryCard icon="▣" label="Card outstanding" value={formatAmount(balanceSummary?.credit_card_outstanding)} action={() => setActiveView("cards")} /></section>
        <section className="dashboard-grid">
          <DashboardCard title="Spending summary" action="View spending" onAction={() => setActiveView("spending")}><p className="month-label">{reportingPeriodLabel(reportingPeriod)}</p><CategoryBars categories={report?.categories ?? []} /></DashboardCard>
          <DashboardCard title="Recent transactions" action="View all" onAction={() => openTransactions("bank_account")}><TransactionList transactions={transactions.slice(0, 5)} onOpen={openTransactionDetails} compact /></DashboardCard>
          <DashboardCard title="Bank accounts" action="Connect Gmail" onAction={() => setActiveView("mailboxes")}><AccountList accounts={bankAccounts} empty="Connect Gmail to discover your bank accounts." onOpen={(id) => openTransactions("bank_account", id)} /></DashboardCard>
          <DashboardCard title="Credit cards" action="View cards" onAction={() => setActiveView("cards")}><AccountList accounts={creditCards} empty="Add a credit card to track card spending separately." onOpen={(id) => openTransactions("credit_card", id)} card /></DashboardCard>
          <DashboardCard title="Upcoming recurring payments" action="Manage" onAction={() => setActiveView("recurring")}><RecurringPaymentList payments={recurringPayments.filter((payment) => payment.state !== "dismissed")} onReview={reviewRecurringPayment} /></DashboardCard>
          <DashboardCard title="Monthly insights"><MonthlyInsightsCard insights={monthlyInsights} /></DashboardCard>
          <DashboardCard title="Budget health" action="Manage budgets" onAction={() => setActiveView("budgets")}><BudgetHealth budgets={budgets} /></DashboardCard>
          <DashboardCard title="Mailbox sync" action="Manage" onAction={() => setActiveView("mailboxes")}><p className="sync-copy"><span className={mailboxes.some((mailbox) => mailbox.connection_status === "connected") ? "status-dot" : "status-dot offline"} />{mailboxes.filter((mailbox) => mailbox.connection_status === "connected").length} connected mailbox{mailboxes.filter((mailbox) => mailbox.connection_status === "connected").length === 1 ? "" : "es"}</p><p className="muted">Connect Gmail to bring transaction alerts and statements into Arcis.</p></DashboardCard>
        </section>
      </> : <HomeLoadingState />)}

      {activeView === "spending" && <section className="page-section spending-page"><div className="spending-toolbar"><div><p className="section-kicker">SPENDING ANALYSIS</p><h2>All spending</h2><p className="muted">A complete view of categorised spending across your available history.</p></div></div><section className="spending-overview"><DashboardCard title="Spending by category"><SpendingDonut summary={spendingSummary} selectedCategoryId={selectedSpendingCategoryId} onSelect={setSelectedSpendingCategoryId} /></DashboardCard><DashboardCard title="Category breakdown"><SpendingCategoryList summary={spendingSummary} selectedCategoryId={selectedSpendingCategoryId} onSelect={setSelectedSpendingCategoryId} onViewTransactions={openCategoryTransactions} /></DashboardCard></section><section className="dashboard-card spending-trend-card"><div className="card-heading"><div><h3>{spendingSummary?.categories.find((category) => category.category_id === selectedSpendingCategoryId)?.category ?? "Select a category"}</h3><p className="muted trend-copy">Complete spending history</p></div><div className="segmented"><button className={spendingGranularity === "monthly" ? "active" : ""} onClick={() => setSpendingGranularity("monthly")}>Monthly</button><button className={spendingGranularity === "yearly" ? "active" : ""} onClick={() => setSpendingGranularity("yearly")}>Yearly</button></div></div><SpendingTrendChart trend={spendingTrend} granularity={spendingGranularity} /></section></section>}

      {activeView === "budgets" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">{formatMonth(currentMonth).toUpperCase()}</p><h2>Monthly budgets</h2></div></div><div className="account-layout"><DashboardCard title="Budget versus actual"><BudgetList budgets={budgets} onRemove={removeBudget} /></DashboardCard><form className="form-card" onSubmit={createBudget}><h3>Create or adjust budget</h3><label className="field-label">Category<select name="category_id" required defaultValue=""><option value="" disabled>Select category</option>{categories.filter((category) => !category.parent_id).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label className="field-label">Monthly limit<input name="monthly_limit" type="number" min="1" step="0.01" placeholder="₹0" required /></label><button type="submit">Save budget</button><p className="hint">Saving the same category updates its current monthly limit.</p></form></div></section>}

      {activeView === "recurring" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">PATTERN DETECTION</p><h2>Recurring & subscriptions</h2></div><button onClick={() => void detectRecurringPayments()}>Scan transactions</button></div><RecurringManager payments={recurringPayments} onReview={reviewRecurringPayment} onUpdate={updateRecurringPayment} /></section>}

      {activeView === "transactions" && <section className="page-section transaction-page"><div className="segmented transaction-tabs" aria-label="Transaction source"><button className={ledgerAccountType === "bank_account" ? "active" : ""} onClick={() => { setLedgerAccountType("bank_account"); setLedgerAccountId(""); }}>Savings accounts</button><button className={ledgerAccountType === "credit_card" ? "active" : ""} onClick={() => { setLedgerAccountType("credit_card"); setLedgerAccountId(""); }}>Credit cards</button></div><div className="ledger-toolbar"><div className="ledger-popover-wrap"><button className="secondary toolbar-button period-button" onClick={() => setShowPeriodPicker(!showPeriodPicker)}>▣ <span>{reportingPeriodLabel(reportingPeriod)}</span></button>{showPeriodPicker && <div className="ledger-popover period-popover">{reportingPeriods.map(([value, label]) => <button key={value} className={value === reportingPeriod ? "period-option selected" : "period-option"} onClick={() => void changeReportingPeriod(value)}>{label}</button>)}</div>}</div><input className="ledger-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" aria-label="Search transactions" /><div className="ledger-popover-wrap"><button className={ledgerAccountId || ledgerCategoryId || ledgerUncategorized ? "secondary toolbar-button active-filter" : "secondary toolbar-button"} onClick={() => setShowLedgerFilters(!showLedgerFilters)} aria-label="Filter transactions"><FilterIcon /></button>{showLedgerFilters && <div className="ledger-popover filter-popover"><label>Account<select value={ledgerAccountId} onChange={(event) => setLedgerAccountId(event.target.value)}><option value="">All accounts</option>{accounts.filter((account) => account.account_type === ledgerAccountType).map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label>Category<select value={ledgerUncategorized ? "__uncategorized__" : ledgerCategoryId} onChange={(event) => { const value = event.target.value; setLedgerUncategorized(value === "__uncategorized__"); setLedgerCategoryId(value === "__uncategorized__" ? "" : value); }}><option value="">All categories</option><option value="__uncategorized__">Uncategorized</option>{categories.filter((category) => !category.parent_id).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>{(ledgerAccountId || ledgerCategoryId || ledgerUncategorized || search.trim() || reportingPeriod !== "all_time") && <button className="secondary clear-filters" onClick={clearLedgerFilters}>Clear filters</button>}</div>}</div>{(ledgerAccountId || ledgerCategoryId || ledgerUncategorized || search.trim() || reportingPeriod !== "all_time") && <button className="text-action ledger-clear-action" onClick={clearLedgerFilters}>Clear filters</button>}</div><TransactionList transactions={transactions} categories={categories} onOpen={openTransactionDetails} onTag={(transaction) => { setTaggingTransaction(transaction); setTagCategoryId(transaction.category_id ?? ""); setTagSubcategoryId(transaction.subcategory_id ?? ""); }} />{nextCursor && <button className="secondary load-more" onClick={() => void loadMore()}>Load more</button>}</section>}

      {activeView === "accounts" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">SAVINGS</p><h2>Bank accounts</h2><p className="muted page-note">Connect Gmail to discover accounts automatically, or add one manually as a fallback.</p></div><button onClick={() => setActiveView("mailboxes")}>Discover from Gmail</button></div><div className="account-layout"><DashboardCard title="Your accounts"><ManagedAccountList accounts={bankAccountDetails} balances={bankAccounts} empty="No confirmed bank accounts yet." onOpen={(id) => openTransactions("bank_account", id)} onEdit={setEditingAccount} onRemove={removeAccount} /></DashboardCard><form className="form-card" onSubmit={createAccount}><h3>Add manually</h3><input name="display_name" placeholder="Display name" required /><input name="institution_code" placeholder="Institution, e.g. icici" required /><input name="product_name" placeholder="Product name" required /><input name="masked_identifier" placeholder="Masked identifier, e.g. XX1234" /><select name="account_type" defaultValue="bank_account"><option value="bank_account">Bank account</option><option value="credit_card">Credit card</option></select><input name="currency" defaultValue="INR" required /><button type="submit">Create account</button></form></div></section>}

      {activeView === "cards" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">CARD SPENDING</p><h2>Credit cards</h2></div><span className="headline-amount">{formatAmount(balanceSummary?.credit_card_outstanding)}</span></div><p className="muted page-note">Credit-card purchases are tracked here and do not change your total bank balance.</p><div className="account-layout"><DashboardCard title="Outstanding by card"><ManagedAccountList accounts={creditCardDetails} balances={creditCards} empty="No credit cards added yet." onOpen={(id) => openTransactions("credit_card", id)} onEdit={setEditingAccount} onRemove={removeAccount} card /></DashboardCard><DashboardCard title="Payment reminders" action="Check due dates" onAction={() => void generateCardReminders()}><NotificationList notifications={notifications.filter((item) => item.notification_kind.startsWith("card_"))} onDismiss={dismissNotification} /></DashboardCard></div><section className="dashboard-card"><div className="card-heading"><h3>Statements and due dates</h3><button className="text-action" onClick={() => openTransactions("bank_account")}>View savings ledger →</button></div><CardStatementList statements={cardStatements} onPaid={markStatementPaid} /></section></section>}

      {activeView === "imports" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">STATEMENTS</p><h2>Imports & reconciliation</h2></div></div><div className="account-layout"><form className="form-card" onSubmit={inspectFile}><h3>Import statement</h3><select value={accountId} onChange={(event) => setAccountId(event.target.value)} required><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select><input type="file" accept=".csv,.xlsx,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required />{file?.name.toLowerCase().endsWith(".pdf") && <input type="password" value={pdfPassword} onChange={(event) => setPdfPassword(event.target.value)} placeholder="PDF password, if required" />}<p className="hint">CSV, XLSX, or PDF · password is used only for this preview</p><button type="submit">Inspect statement</button></form><DashboardCard title="Import history"><ImportList imports={imports} onOpen={openImport} onCancel={cancelImport} /></DashboardCard></div>{inspection && <section className="panel"><h3>Column mapping · {file?.name}</h3><p className="muted">Review the detected columns before parsing the statement.</p><div className="mapping-grid">{mappingFields.map(([field, label, required]) => <label key={field}>{label}{required ? " *" : ""}<select value={mapping[field] ?? ""} onChange={(event) => setMapping({ ...mapping, [field]: event.target.value })}><option value="">{required ? "Select column" : "Not available"}</option>{inspection.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select></label>)}</div><button onClick={() => void createPreview()}>Create preview</button></section>}{preview && <section className="panel"><h3>Import preview · {preview.import.filename}</h3><p className="muted">{preview.import.valid_row_count} valid and {preview.import.invalid_row_count} invalid rows from {preview.import.row_count} source rows.</p>{preview.statement && <p className="hint">Parser: {preview.statement.parser_name} · Statement amount: {formatAmount(preview.statement.statement_amount)} · Minimum due: {formatAmount(preview.statement.minimum_due)} · Due: {preview.statement.due_date ?? "—"}</p>}{preview.errors.length > 0 && <div className="import-errors"><h4>Rows needing review</h4><ul>{preview.errors.map((error) => <li key={error.ordinal}>Row {error.ordinal}: {error.message}</li>)}</ul></div>}<TransactionList transactions={preview.rows} />{preview.import.state === "preview_ready" && <button onClick={confirmImport}>Confirm valid rows</button>}</section>}<section className="panel"><h3>Statement reconciliation review</h3>{reconciliationReviews.length ? <div className="table-wrap"><table><thead><tr><th>Statement row</th><th>Ledger candidate</th><th>Match</th><th>Decision</th></tr></thead><tbody>{reconciliationReviews.map((review) => <tr key={review.id}><td>{review.transaction_date} · {review.narration} · {formatAmount(review.amount)}</td><td>{review.candidate_date ?? "—"} · {review.candidate_narration ?? "No candidate"}</td><td>{review.match_method} ({review.match_score})</td><td><button className="secondary" onClick={() => void resolveReconciliation(review.id, "accepted")}>Accept</button> <button className="secondary" onClick={() => void resolveReconciliation(review.id, "rejected")}>Reject</button></td></tr>)}</tbody></table></div> : <p className="muted">No uncertain statement matches need a decision.</p>}</section></section>}

      {activeView === "notifications" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">ACTIVITY</p><h2>Notifications</h2><p className="muted page-note">Gmail scan results, statement actions, reminders, and other account activity.</p></div></div><section className="dashboard-card"><NotificationList notifications={notifications} onDismiss={dismissNotification} onAction={openNotificationAction} empty="No unread notifications." /></section></section>}

      {activeView === "privacy" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">DATA CONTROL</p><h2>Privacy</h2><p className="muted page-note">Understand what Arcis stores and control how long source files are retained.</p></div><button onClick={() => void downloadPrivacyExport()}>Download my data</button></div>{privacyInventory && <section className="privacy-inventory" aria-label="Stored data summary"><PrivacyStat label="Accounts" value={privacyInventory.accounts} /><PrivacyStat label="Transactions" value={privacyInventory.transactions} /><PrivacyStat label="Stored source files" value={privacyInventory.stored_documents} /><PrivacyStat label="Connected mailboxes" value={privacyInventory.connected_mailboxes} /></section>}<div className="account-layout"><form className="form-card" onSubmit={updateRetention}><h3>Source-file retention</h3><label className="field-label">Email source artifacts<input name="source_artifacts_days" type="number" min="30" max="3650" defaultValue={privacyInventory?.retention_policy.source_artifacts_days ?? 365} required /><small>Days to retain raw email sources.</small></label><label className="field-label">Statement files<input name="statement_files_days" type="number" min="30" max="3650" defaultValue={privacyInventory?.retention_policy.statement_files_days ?? 730} required /><small>Days to retain uploaded and emailed statements.</small></label><button type="submit">Save retention policy</button><button type="button" className="secondary" onClick={() => void enforceRetention()}>Apply policy now</button><p className="hint">The policy runs daily. Deleted source files have a 30-day recovery window before permanent purge.</p></form><DashboardCard title="Privacy guarantees"><ul className="privacy-promises"><li>OAuth and PDF passwords are never included in exports.</li><li>Raw email bodies and statement files are not sent to AI services.</li><li>Exports include normalized financial data and safe source metadata only.</li><li>Retention cleanup preserves confirmed ledger provenance.</li></ul></DashboardCard></div></section>}

      {activeView === "mailboxes" && <section className="page-section">
        <div className="section-heading mailbox-heading"><p className="section-kicker">GMAIL</p><a className="button-link" href={`${API_URL}/api/v1/oauth/gmail/start`}>Connect Gmail</a></div>
        <section className="panel"><h3>Connected mailboxes</h3>{mailboxes.length ? <><div className="table-wrap"><table><thead><tr><th>Mailbox</th><th>Status</th><th>Last sync</th><th /></tr></thead><tbody>{mailboxes.map((mailbox) => <tr key={mailbox.id}><td>{mailbox.display_email}</td><td><span className="status-chip">{mailbox.connection_status}</span></td><td>{mailbox.last_successful_sync_at ? new Date(mailbox.last_successful_sync_at).toLocaleString() : "Not yet synced"}</td><td><span className="mailbox-actions">{mailbox.connection_status === "connected" ? <><button className="secondary" onClick={() => void discoverMailboxAccounts(mailbox.id)}>Scan accounts & cards</button><button className="secondary" onClick={() => void syncMailbox(mailbox.id)}>Sync now</button><button className="secondary danger" onClick={() => void disconnectMailbox(mailbox.id)}>Disconnect</button></> : <span className="muted">Reconnect with Gmail OAuth</span>}</span></td></tr>)}</tbody></table></div><form className="backfill" onSubmit={backfillMailbox}><h3>Advanced historical email import</h3><select value={backfillMailboxId} onChange={(event) => setBackfillMailboxId(event.target.value)}>{mailboxes.filter((mailbox) => mailbox.connection_status === "connected").map((mailbox) => <option key={mailbox.id} value={mailbox.id}>{mailbox.display_email}</option>)}</select><input value={backfillQuery} onChange={(event) => setBackfillQuery(event.target.value)} aria-label="Gmail backfill query" /><button type="submit">Import matching emails</button></form></> : <p className="muted">Connect a Gmail mailbox to begin. You do not need to add accounts manually first.</p>}</section>
        <DiscoveredAccountsPanel accounts={discoveredAccounts} onConfirm={confirmDiscoveredAccount} onReject={rejectDiscoveredAccount} onReconsider={reconsiderDiscoveredAccount} />
      </section>}

      {statementNotification && <div className="detail-backdrop" role="dialog" aria-modal="true" aria-labelledby="statement-password-title"><form className="statement-password-sheet" onSubmit={confirmStatementNotification}><div className="detail-heading"><button type="button" className="icon-button" autoFocus onClick={() => setStatementNotification(null)} aria-label="Close statement password confirmation">×</button><p className="section-kicker" id="statement-password-title">CONFIRM STATEMENT</p><span /></div><div className="statement-password-body"><h2>{statementNotification.title}</h2><p className="muted">{statementNotification.body}</p><aside className="password-guidance"><strong>Password guidance from email</strong><span>{statementNotification.action_payload.password_hint ?? "Check the bank's statement email for its PDF password instructions."}</span></aside><label className="field-label">Savings account<select value={accountId} onChange={(event) => setAccountId(event.target.value)} required><option value="">Select account</option>{bankAccountDetails.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label className="field-label">PDF password<input type="password" value={pdfPassword} onChange={(event) => setPdfPassword(event.target.value)} autoComplete="off" placeholder="Enter the password described in the email" required /></label><p className="hint">The password is used only to open this statement and is never stored.</p><button type="submit">Open statement preview</button></div></form></div>}
      {editingAccount && <div className="detail-backdrop" role="dialog" aria-modal="true" aria-labelledby="account-dialog-title"><form className="account-edit-sheet" onSubmit={updateAccount}><div className="detail-heading"><button type="button" className="icon-button" autoFocus onClick={() => setEditingAccount(null)} aria-label="Close account editor">×</button><p className="section-kicker" id="account-dialog-title">EDIT {editingAccount.account_type === "credit_card" ? "CARD" : "ACCOUNT"}</p><span /></div><div className="account-edit-body"><div className="account-edit-identity"><span className={`account-mark ${editingAccount.account_type === "credit_card" ? "card" : ""}`}><BankMark institutionCode={editingAccount.institution_code} fallback={editingAccount.account_type === "credit_card" ? "▣" : "₹"} /></span><div><strong>{editingAccount.institution_code.toUpperCase()}</strong><small>{editingAccount.account_type === "credit_card" ? "Credit card" : "Savings account"}</small></div></div><label className="field-label">Display name<input name="display_name" defaultValue={editingAccount.display_name} required /></label><label className="field-label">Product name<input name="product_name" defaultValue={editingAccount.product_name} required /></label><label className="field-label">Masked identifier<input name="masked_identifier" defaultValue={editingAccount.masked_identifier ?? ""} placeholder="e.g. ••••1234" /></label><label className="field-label">Currency<input name="currency" defaultValue={editingAccount.currency} maxLength={3} required /></label><div className="account-edit-actions"><button type="submit">Save changes</button><button type="button" className="secondary danger" onClick={() => void removeAccount(editingAccount)}>Remove {editingAccount.account_type === "credit_card" ? "card" : "account"}</button></div><p className="hint">Removing archives this product and skips future matching Gmail alerts. Existing financial history is retained.</p></div></form></div>}
      {selectedTransaction && <div className="detail-backdrop" role="dialog" aria-modal="true" aria-labelledby="transaction-dialog-title"><section className="detail-sheet"><div className="detail-heading"><button className="icon-button" autoFocus onClick={() => setSelectedTransaction(null)} aria-label="Close transaction details">×</button><p className="section-kicker" id="transaction-dialog-title">TRANSACTION</p><span /></div><div className="transaction-overview"><span className={selectedTransaction.direction === "credit" ? "amount credit" : "amount debit"}>{selectedTransaction.direction === "credit" ? "+" : "−"}{formatAmount(selectedTransaction.amount)}</span><button className="category-pill" onClick={() => { setTaggingTransaction(selectedTransaction); setTagCategoryId(selectedTransaction.category_id ?? ""); setTagSubcategoryId(selectedTransaction.subcategory_id ?? ""); }}>{transactionCategoryLabel(selectedTransaction, categories) ?? "Tag transaction"}</button></div><div className="transaction-summary"><Detail label="From" value={selectedTransaction.account_name} /><Detail label="On" value={formatLongDate(selectedTransaction.transaction_date)} /><button className="paid-to" onClick={() => { setTaggingTransaction(selectedTransaction); setTagCategoryId(selectedTransaction.category_id ?? ""); setTagSubcategoryId(selectedTransaction.subcategory_id ?? ""); }}><span>Paid to</span><strong>{selectedTransaction.merchant_normalized ?? selectedTransaction.narration}</strong><b>›</b></button></div><div className="detail-rows"><button className="detail-row" onClick={() => setShowTransactionMoreDetails(!showTransactionMoreDetails)}><span>More details</span><b>{showTransactionMoreDetails ? "⌃" : "›"}</b></button>{showTransactionMoreDetails && <div className="expanded-details"><Detail label="Summary" value={`${selectedTransaction.direction === "credit" ? "Received from" : "Paid to"} ${selectedTransaction.merchant_normalized ?? selectedTransaction.narration} on ${formatLongDate(selectedTransaction.transaction_date)}`} /><Detail label="Transaction type" value={selectedTransaction.direction === "credit" ? "Incoming" : "Outgoing"} /><Detail label="Narration" value={selectedTransaction.narration} /><Detail label="Transaction ID" value={selectedTransaction.id} /><Detail label="Transaction date" value={selectedTransaction.transaction_date} /><Detail label="Reference / UTR" value={selectedTransaction.provider_reference ?? "Not available"} /><button className="text-action evidence-action" onClick={() => void showEvidence(selectedTransaction.id)}>View source evidence</button></div>}</div></section></div>}
      {taggingTransaction && <TagTransactionSheet transaction={taggingTransaction} categories={categories} selectedCategoryId={tagCategoryId} selectedSubcategoryId={tagSubcategoryId} onSelectCategory={(categoryId) => { setTagCategoryId(categoryId); setTagSubcategoryId(""); }} onSelectSubcategory={(categoryId, subcategoryId) => { setTagCategoryId(categoryId); setTagSubcategoryId(subcategoryId); }} onClose={() => setTaggingTransaction(null)} onSave={() => void saveTaggedCategory()} />}
      {categoryMatchPrompt && <div className="detail-backdrop" role="dialog" aria-modal="true" aria-labelledby="category-match-title"><section className="match-confirmation"><p className="section-kicker">MATCHING VENDOR</p><h2 id="category-match-title">Tag {categoryMatchPrompt.count} more transaction{categoryMatchPrompt.count === 1 ? "" : "s"}?</h2><p>Arcis found {categoryMatchPrompt.count} other uncategorized transaction{categoryMatchPrompt.count === 1 ? "" : "s"} from <strong>{categoryMatchPrompt.merchant}</strong>.</p><p className="hint">Apply <strong>{categoryMatchPrompt.category}</strong> to these matches? Transactions that already have a category will not be changed.</p><div className="match-confirmation-actions"><button className="secondary" autoFocus onClick={() => setCategoryMatchPrompt(null)}>Not now</button><button onClick={() => void applyCategoryToMatches()}>Tag {categoryMatchPrompt.count} transaction{categoryMatchPrompt.count === 1 ? "" : "s"}</button></div><small>Future transactions from this vendor will be tagged automatically either way.</small></section></div>}
      {evidence && <div className="detail-backdrop" role="dialog" aria-modal="true" aria-labelledby="evidence-dialog-title"><section className="detail-sheet evidence-sheet"><div className="detail-heading"><span /><h2 id="evidence-dialog-title">Transaction evidence</h2><button className="icon-button" autoFocus onClick={() => setEvidence(null)} aria-label="Close evidence">×</button></div>{evidence.length ? <pre>{JSON.stringify(evidence, null, 2)}</pre> : <p className="muted">No source evidence found.</p>}</section></div>}
    </div>
  </main>;
}

function SummaryCard({ icon, label, value, tone, action }: { icon: string; label: string; value: string; tone?: string; action?: () => void }) { return <button className={`summary-card ${tone ?? ""}`} onClick={action}><span>{icon}</span><small>{label}</small><strong>{value}</strong></button>; }
function HomeLoadingState() { return <section className="home-loading" aria-label="Loading dashboard" aria-live="polite"><div className="loading-hero"><span className="loading-line short" /><span className="loading-line amount" /><span className="loading-line medium" /></div><div className="loading-summary"><i /><i /><i /></div><div className="loading-cards"><i /><i /><i /><i /></div><span className="sr-only">Loading your financial overview.</span></section>; }
function DiscoveredAccountsPanel({ accounts, onConfirm, onReject, onReconsider }: { accounts: DiscoveredAccount[]; onConfirm: (event: FormEvent<HTMLFormElement>, id: string) => void; onReject: (id: string) => void; onReconsider: (id: string) => void }) {
  const pending = accounts.filter((account) => account.state === "pending");
  const decided = accounts.filter((account) => account.state !== "pending");
  return <section className="panel discovery-panel">
    <div className="card-heading"><div><h3>Detected accounts and cards</h3><p className="muted">Nothing enters your accounts, transactions, balances, or spending until you confirm it.</p></div><span className="status-chip">{pending.length} awaiting review</span></div>
    {pending.length ? <div className="discovery-grid">{pending.map((account) => <form className="discovery-card" key={account.id} onSubmit={(event) => onConfirm(event, account.id)}>
      <div className="discovery-product"><span className={`account-mark ${account.account_type === "credit_card" ? "card" : ""}`}><BankMark institutionCode={account.institution_code} fallback={account.account_type === "credit_card" ? "▣" : "₹"} /></span><div><p className="section-kicker">{account.account_type === "credit_card" ? "CREDIT CARD" : "BANK ACCOUNT"}</p><h4>{account.institution_code.toUpperCase()} {account.masked_identifier}</h4><small>{account.transaction_alert_count} matching alert{Number(account.transaction_alert_count) === 1 ? "" : "s"} · {account.mailbox_email}</small></div></div>
      <label className="field-label">Product name<input name="product_name" defaultValue={account.suggested_product_name} required /></label>
      <label className="field-label">Display name<input name="display_name" defaultValue={account.suggested_display_name} required /></label>
      <label className="field-label currency-field">Currency<input name="currency" defaultValue={account.currency} maxLength={3} required /></label>
      <div className="discovery-actions"><button type="submit">Confirm & add</button><button type="button" className="secondary danger" onClick={() => onReject(account.id)}>Ignore</button></div>
    </form>)}</div> : <div className="discovery-empty"><strong>No products waiting for confirmation</strong><span>Use “Scan accounts & cards” on a connected mailbox to look for supported alerts.</span></div>}
    {decided.length > 0 && <details className="discovery-history"><summary>Reviewed products ({decided.length})</summary><div>{decided.map((account) => <article key={account.id}><span><strong>{account.suggested_display_name}</strong><small>{account.state === "confirmed" ? "Added to Arcis" : "Ignored — future alerts are skipped"}</small></span><em className={`state ${account.state}`}>{account.state}</em>{account.state === "rejected" && <button className="secondary mini" onClick={() => onReconsider(account.id)}>Review again</button>}</article>)}</div></details>}
  </section>;
}

function DashboardCard({ title, action, onAction, children }: { title: string; action?: string; onAction?: () => void; children: ReactNode }) { return <section className="dashboard-card"><div className="card-heading"><h3>{title}</h3>{action && <button className="text-action" onClick={onAction}>{action} →</button>}</div>{children}</section>; }
function MonthlyInsightsCard({ insights }: { insights: MonthlyInsights | null }) { if (!insights?.forecast) return <p className="muted">Add this month’s transactions to see a forecast and evidence-linked anomalies.</p>; return <div className="insights-card"><p><span>Projected month-end spend</span><strong>{formatAmount(insights.forecast.projected_expense)}</strong><small>Based on {insights.forecast.days_observed} of {insights.forecast.days_in_month} days observed.</small></p>{insights.anomalies.length ? <div className="insight-list">{insights.anomalies.slice(0, 3).map((insight, index) => <article key={`${insight.kind}-${index}`}><strong>{insight.title}</strong><span>{insight.reason}</span></article>)}</div> : <p className="muted">No unusual spending patterns were found for this month.</p>}</div>; }

function RecurringPaymentList({ payments, onReview }: { payments: RecurringPayment[]; onReview: (id: string, state: "confirmed" | "dismissed") => void }) { if (!payments.length) return <p className="muted">No recurring patterns found yet. Scan after you have a few months of history.</p>; return <div className="recurring-list">{payments.slice(0, 4).map((payment) => <article key={payment.id}><span><strong>{payment.display_name}</strong><small>{payment.cadence} · expected {formatShortDate(payment.next_expected_on)} · {payment.account_name}</small></span><b>{formatAmount(payment.typical_amount)}</b>{payment.state === "detected" && <span className="recurring-actions"><button className="secondary mini" onClick={() => onReview(payment.id, "confirmed")}>Confirm</button><button className="secondary mini" onClick={() => onReview(payment.id, "dismissed")}>Dismiss</button></span>}</article>)}</div>; }
function RecurringManager({ payments, onReview, onUpdate }: { payments: RecurringPayment[]; onReview: (id: string, state: "detected" | "confirmed" | "dismissed") => void; onUpdate: (id: string, payload: { display_name: string; typical_amount: string; next_expected_on: string }) => Promise<void> }) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const confirmed = payments.filter((payment) => payment.state === "confirmed");
  const monthly = confirmed.reduce((sum, payment) => sum + Number(payment.monthly_equivalent), 0);
  async function saveEdit(event: FormEvent<HTMLFormElement>, payment: RecurringPayment) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    await onUpdate(payment.id, {
      display_name: String(values.display_name),
      typical_amount: String(values.typical_amount),
      next_expected_on: String(values.next_expected_on),
    });
    setEditingId(null);
  }
  const renderItems = (state: RecurringPayment["state"]) => {
    const items = payments.filter((payment) => payment.state === state);
    if (!items.length) return <p className="muted">No {state} patterns.</p>;
    return <div className="recurring-manager-list">{items.map((payment) => editingId === payment.id
      ? <form className="recurring-edit" key={payment.id} onSubmit={(event) => void saveEdit(event, payment)}>
          <label>Name<input name="display_name" defaultValue={payment.display_name} required /></label>
          <label>Expected amount<input name="typical_amount" type="number" min="0.01" step="0.01" defaultValue={payment.typical_amount} required /></label>
          <label>Next expected date<input name="next_expected_on" type="date" defaultValue={payment.next_expected_on} required /></label>
          <span><button type="submit">Save</button><button type="button" className="secondary" onClick={() => setEditingId(null)}>Cancel</button></span>
        </form>
      : <article key={payment.id}>
          <span className={`recurring-kind ${payment.kind}`}>{payment.kind}</span>
          <div><strong>{payment.display_name}</strong><small>{payment.account_name} · {payment.cadence} · {payment.occurrence_count} occurrences</small><small>Next expected {formatLongDate(payment.next_expected_on)}</small></div>
          <b>{formatAmount(payment.typical_amount)}</b>
          <span className="recurring-manager-actions"><button className="secondary mini" onClick={() => setEditingId(payment.id)}>Edit</button>{state === "detected" && <><button className="secondary mini" onClick={() => onReview(payment.id, "confirmed")}>Confirm</button><button className="secondary mini" onClick={() => onReview(payment.id, "dismissed")}>Dismiss</button></>}{state === "confirmed" && <button className="secondary mini" onClick={() => onReview(payment.id, "dismissed")}>Dismiss</button>}{state === "dismissed" && <button className="secondary mini" onClick={() => onReview(payment.id, "detected")}>Restore</button>}</span>
        </article>)}</div>;
  };
  return <><section className="recurring-commitments"><div><span>Confirmed monthly commitment</span><strong>{formatAmount(String(monthly))}</strong></div><div><span>Estimated annual commitment</span><strong>{formatAmount(String(monthly * 12))}</strong></div></section><section className="dashboard-grid"><DashboardCard title="Suggestions">{renderItems("detected")}</DashboardCard><DashboardCard title="Confirmed">{renderItems("confirmed")}</DashboardCard><DashboardCard title="Dismissed">{renderItems("dismissed")}</DashboardCard></section></>;
}
function BudgetHealth({ budgets }: { budgets: Budget[] }) { const active = budgets.filter((budget) => budget.active); if (!active.length) return <p className="muted">Create category budgets to compare this month’s spending with your plan.</p>; const limit = active.reduce((sum, budget) => sum + Number(budget.monthly_limit), 0); const spent = active.reduce((sum, budget) => sum + Number(budget.spent), 0); const percentage = limit ? spent / limit * 100 : 0; return <div className="budget-health"><div><strong>{Math.round(percentage)}%</strong><span>of total budget used</span></div><progress max="100" value={Math.min(percentage, 100)} /><small>{formatAmount(String(spent))} of {formatAmount(String(limit))} · {active.filter((budget) => budget.over_budget).length} over budget</small></div>; }
function BudgetList({ budgets, onRemove }: { budgets: Budget[]; onRemove: (id: string) => void }) { if (!budgets.length) return <p className="muted">No budgets yet. Create one for a category to start tracking it.</p>; return <div className="budget-list">{budgets.map((budget) => <article key={budget.id} className={budget.over_budget ? "over" : ""}><div><strong>{budget.category}</strong><span>{formatAmount(budget.spent)} of {formatAmount(budget.monthly_limit)}</span></div><b>{budget.over_budget ? `${formatAmount(String(Math.abs(Number(budget.remaining))))} over` : `${formatAmount(budget.remaining)} left`}</b><progress max="100" value={Math.min(Number(budget.percentage), 100)} /><small>{Number(budget.percentage).toFixed(0)}% used</small><button className="secondary mini" onClick={() => onRemove(budget.id)}>Remove</button></article>)}</div>; }
function NotificationList({ notifications, onDismiss, onAction, empty = "No upcoming or overdue card reminders." }: { notifications: NotificationItem[]; onDismiss: (id: string) => void; onAction?: (notification: NotificationItem) => void; empty?: string }) { if (!notifications.length) return <p className="muted">{empty}</p>; return <div className="notification-list">{notifications.map((notification) => <article key={notification.id}><span className={notification.notification_kind.includes("overdue") ? "notification-mark overdue" : "notification-mark"}>!</span><div><strong>{notification.title}</strong><small>{notification.body}</small></div><span className="notification-actions">{notification.action_kind && onAction && <button className="mini" onClick={() => onAction(notification)}>Review</button>}<button className="secondary mini" onClick={() => onDismiss(notification.id)}>Dismiss</button></span></article>)}</div>; }
function CardStatementList({ statements, onPaid }: { statements: CardStatement[]; onPaid: (id: string, amount: string | null) => void }) { if (!statements.length) return <p className="muted">Import a supported credit-card statement to see its amount and due date.</p>; return <div className="card-statement-list">{statements.map((statement) => <article key={statement.id}><div><strong>{statement.account_name}</strong><small>{statement.period_end ? `Statement ending ${formatLongDate(statement.period_end)}` : "Statement period unavailable"}</small></div><span><small>Statement</small><b>{formatAmount(statement.statement_amount)}</b></span><span><small>Minimum due</small><b>{formatAmount(statement.minimum_due)}</b></span><span><small>Due date</small><b>{statement.due_date ? formatLongDate(statement.due_date) : "Not available"}</b></span><em className={`payment-state ${statement.payment_status}`}>{statement.payment_status}</em>{statement.payment_status !== "paid" && <button className="secondary mini" onClick={() => onPaid(statement.id, statement.statement_amount)}>Mark paid</button>}</article>)}</div>; }

function AccountList({ accounts, empty, onOpen, card = false }: { accounts: AccountBalance[]; empty: string; onOpen: (id: string) => void; card?: boolean }) { if (!accounts.length) return <p className="muted">{empty}</p>; return <div className="account-list">{accounts.map((account) => <button key={account.id} className="account-row" onClick={() => onOpen(account.id)}><span className={`account-mark ${card ? "card" : ""}`}><BankMark institutionCode={account.institution_code} fallback={card ? "▣" : "₹"} /></span><span><strong>{account.display_name}</strong><small>{card ? "Card outstanding" : balanceSourceLabel(account)}</small></span><b className={card ? "card-balance" : ""}>{account.balance === null ? "Unavailable" : formatAmount(card ? String(Math.abs(Number(account.balance))) : account.balance)}</b></button>)}</div>; }

function ManagedAccountList({ accounts, balances, empty, onOpen, onEdit, onRemove, card = false }: { accounts: Account[]; balances: AccountBalance[]; empty: string; onOpen: (id: string) => void; onEdit: (account: Account) => void; onRemove: (account: Account) => void; card?: boolean }) {
  if (!accounts.length) return <p className="muted">{empty}</p>;
  const balanceById = new Map(balances.map((account) => [account.id, account.balance]));
  return <div className="managed-account-list">{accounts.map((account) => { const balance = balanceById.get(account.id); return <article className="managed-account-row" key={account.id}><button className="managed-account-main" onClick={() => onOpen(account.id)}><span className={`account-mark ${card ? "card" : ""}`}><BankMark institutionCode={account.institution_code} fallback={card ? "▣" : "₹"} /></span><span><strong>{account.display_name}</strong><small>{account.product_name} · {account.masked_identifier ?? "Identifier unavailable"}</small></span><b>{balance == null ? "Unavailable" : formatAmount(card ? String(Math.abs(Number(balance))) : balance)}</b></button><div className="managed-account-actions"><button className="secondary mini" onClick={() => onEdit(account)}>Edit</button><button className="secondary mini danger" onClick={() => onRemove(account)}>Remove</button></div></article>; })}</div>;
}

function FilterIcon() { return <svg className="filter-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="11" cy="18" r="2" /></svg>; }

function BankMark({ institutionCode, fallback }: { institutionCode?: string; fallback: string }) {
  const code = institutionCode?.toLowerCase();
  const logo = code === "hdfc" ? { src: "https://upload.wikimedia.org/wikipedia/commons/2/28/HDFC_Bank_Logo.svg", alt: "HDFC Bank" } : code === "icici" ? { src: "https://upload.wikimedia.org/wikipedia/commons/1/12/ICICI_Bank_Logo.svg", alt: "ICICI Bank" } : null;
  return logo ? <img className={`bank-mark-logo ${code}`} src={logo.src} alt={logo.alt} /> : <span className="bank-mark-fallback">{fallback}</span>;
}
function CategoryBars({ categories }: { categories: Report["categories"] }) { const debits = categories.filter((category) => category.direction !== "credit").slice(0, 5); const largest = Math.max(...debits.map((category) => Number(category.amount)), 1); if (!debits.length) return <p className="muted">No categorized spending for this month yet.</p>; return <div className="category-bars">{debits.map((category) => <div key={category.category} className="category-bar"><div><span>{category.category}</span><b>{formatAmount(category.amount)}</b></div><i><em style={{ width: `${Math.max(7, (Number(category.amount) / largest) * 100)}%` }} /></i></div>)}</div>; }
const spendingColours = ["#7790f0", "#55c79b", "#e28a66", "#ba7ee9", "#e06d8c", "#d9b45d", "#66b7d9", "#9cc776"];
function SpendingDonut({ summary, selectedCategoryId, onSelect }: { summary: SpendingSummary | null; selectedCategoryId: string; onSelect: (id: string) => void }) { const categories = summary?.categories ?? []; if (!categories.length) return <p className="muted">Categorise debit transactions to see the spending breakdown.</p>; const circumference = 263.894; let offset = 0; return <div className="spending-donut-wrap"><div className="spending-donut" role="img" aria-label="All-time spending by category"><svg viewBox="0 0 100 100" aria-hidden="true"><circle className="donut-track" cx="50" cy="50" r="42" />{categories.map((category, index) => { const length = Number(category.percentage) / 100 * circumference; const dashOffset = -offset; offset += length; return <circle key={category.category} className={category.category_id === selectedCategoryId ? "donut-slice selected" : "donut-slice"} cx="50" cy="50" r="42" stroke={spendingColours[index % spendingColours.length]} strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={dashOffset} onClick={() => category.category_id && onSelect(category.category_id)} />; })}</svg><span><small>Total spending</small><strong>{formatAmount(summary?.expense)}</strong></span></div><p className="muted donut-note">Select a category in the breakdown to explore its trend.</p></div>; }
function SpendingCategoryList({ summary, selectedCategoryId, onSelect, onViewTransactions }: { summary: SpendingSummary | null; selectedCategoryId: string; onSelect: (id: string) => void; onViewTransactions: (id: string | null) => void }) {
  const categories = summary?.categories ?? [];
  if (!categories.length) return <p className="muted">No categorised spending in this period yet.</p>;
  return <div className="spending-category-list">{categories.map((category, index) => <article key={category.category} className={category.category_id === selectedCategoryId ? "selected" : ""}>
    <button className="spending-category-main" disabled={!category.category_id} onClick={() => category.category_id && onSelect(category.category_id)}>
      <i style={{ background: spendingColours[index % spendingColours.length] }} />
      <span><strong>{category.category}</strong><small>{Number(category.percentage).toFixed(1)}%</small></span>
      <b>{formatAmount(category.amount)}</b>
    </button>
    <button className="spending-transactions-link" onClick={() => onViewTransactions(category.category_id)}>Show transactions →</button>
  </article>)}</div>;
}
function SpendingTrendChart({ trend, granularity }: { trend: SpendingTrend | null; granularity: "monthly" | "yearly" }) { const [hoveredIndex, setHoveredIndex] = useState<number | null>(null); const points = trend?.points ?? []; const maximum = Math.max(...points.map((point) => Number(point.amount)), 1); const plotted = points.map((point, index) => ({ point, x: points.length === 1 ? 50 : 5 + (index / (points.length - 1)) * 90, y: 90 - (Number(point.amount) / maximum) * 72 })); const coordinates = plotted.map(({ x, y }) => `${x},${y}`).join(" "); const labelStride = Math.max(1, Math.ceil(points.length / 12)); const hovered = hoveredIndex === null ? null : plotted[hoveredIndex]; if (!trend) return <p className="muted">Choose a category to view its {granularity} spending trend.</p>; return <div className="trend-chart"><div className="trend-axis"><span>{formatAmount(String(maximum))}</span><span>₹0</span></div><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label={`${granularity} spending trend`} onMouseLeave={() => setHoveredIndex(null)}><line x1="5" y1="90" x2="95" y2="90" /><line x1="5" y1="54" x2="95" y2="54" /><line x1="5" y1="18" x2="95" y2="18" />{coordinates && <polyline points={coordinates} />}{plotted.map(({ point, x, y }, index) => <g key={point.period}><circle className="trend-hit" cx={x} cy={y} r="4.5" onMouseEnter={() => setHoveredIndex(index)} /><circle className={hoveredIndex === index ? "trend-point active" : "trend-point"} cx={x} cy={y} r="1.6" /></g>)}</svg>{hovered && <div className="trend-tooltip" style={{ left: `${hovered.x}%`, top: `${Math.max(7, hovered.y - 10)}%` }}><strong>{formatTrendPeriod(hovered.point.period, granularity)}</strong><span>{formatAmount(hovered.point.amount)}</span></div>}<div className="trend-labels">{points.map((point, index) => <span key={point.period}>{index % labelStride === 0 || index === points.length - 1 ? formatTrendPeriod(point.period, granularity) : ""}</span>)}</div></div>; }
function TransactionList({ transactions, categories, onOpen, onTag, compact = false }: { transactions: Transaction[]; categories?: Category[]; onOpen?: (transaction: Transaction) => void; onTag?: (transaction: Transaction) => void; compact?: boolean }) {
  if (!transactions.length) return <p className="muted">No transactions found.</p>;
  return <div className={`transaction-list ${compact ? "compact" : ""}`}>
    {transactions.map((transaction) => <article className="transaction-card" key={transaction.id}>
      <button className="transaction-main" onClick={() => onOpen?.(transaction)}>
        <span className={`transaction-icon ${transaction.direction === "credit" ? "credit" : ""}`}>{transaction.direction === "credit" ? "↙" : "↗"}</span>
        <span className="transaction-copy"><strong>{transaction.merchant_normalized ?? transaction.narration}</strong><small>{transaction.account_name} · {formatShortDate(transaction.transaction_date)}</small></span>
        <span className={transaction.direction === "credit" ? "amount credit" : "amount debit"}>{transaction.direction === "credit" ? "+" : "−"}{formatAmount(transaction.amount)}</span>
      </button>
      {!compact && <div className="transaction-meta">
        <button className="category-pill" onClick={() => onTag?.(transaction)}>{transactionCategoryLabel(transaction, categories) ?? "Tag transaction"}</button>
      </div>}
    </article>)}
  </div>;
}
function TagTransactionSheet({ transaction, categories, selectedCategoryId, selectedSubcategoryId, onSelectCategory, onSelectSubcategory, onClose, onSave }: { transaction: Transaction; categories: Category[]; selectedCategoryId: string; selectedSubcategoryId: string; onSelectCategory: (id: string) => void; onSelectSubcategory: (categoryId: string, subcategoryId: string) => void; onClose: () => void; onSave: () => void }) {
  const [categorySearch, setCategorySearch] = useState("");
  const transactionText = `${transaction.merchant_normalized ?? ""} ${transaction.narration}`.toLocaleLowerCase();
  const searchText = categorySearch.trim().toLocaleLowerCase();
  const childrenByParent = new Map(
    categories.filter((category) => category.parent_id).map((category) => [
      category.parent_id!,
      categories.filter((item) => item.parent_id === category.parent_id),
    ]),
  );
  const relevance = (category: Category) => {
    const children = childrenByParent.get(category.id) ?? [];
    const terms = [category.name, ...children.map((child) => child.name)].map((term) => term.toLocaleLowerCase());
    const transactionMatch = terms.some((term) => term.length > 2 && transactionText.includes(term)) ? 100000 : 0;
    const selected = selectedCategoryId === category.id ? 1000000 : 0;
    return selected + transactionMatch + Number(category.usage_count ?? 0);
  };
  const parents = categories
    .filter((category) => !category.parent_id)
    .filter((parent) => {
      if (!searchText) return true;
      const children = childrenByParent.get(parent.id) ?? [];
      return parent.name.toLocaleLowerCase().includes(searchText)
        || children.some((child) => child.name.toLocaleLowerCase().includes(searchText));
    })
    .sort((left, right) => relevance(right) - relevance(left) || left.name.localeCompare(right.name));
  const frequent = categories
    .filter((category) => !category.parent_id && Number(category.usage_count ?? 0) > 0)
    .sort((left, right) => Number(right.usage_count ?? 0) - Number(left.usage_count ?? 0))
    .slice(0, 5);
  return <div className="tag-backdrop" role="dialog" aria-modal="true" aria-labelledby="tag-dialog-title">
    <section className="tag-sheet"><header className="tag-header"><button className="tag-close" autoFocus onClick={onClose} aria-label="Close tagging">×</button><h2 id="tag-dialog-title">Tag transaction</h2><button className="tag-save" onClick={onSave} disabled={!selectedCategoryId} aria-label="Save category">✓</button></header>
      <article className="tag-transaction"><div><span className="transaction-icon">✎</span><strong>{transaction.merchant_normalized ?? transaction.narration}</strong></div><time>{formatShortDate(transaction.transaction_date)}</time><b className={transaction.direction === "credit" ? "credit" : "debit"}>{transaction.direction === "credit" ? "+" : "−"}{formatAmount(transaction.amount)}</b><p>Narration: {transaction.narration}</p></article>
      <label className="tag-search">⌕ <input value={categorySearch} onChange={(event) => setCategorySearch(event.target.value)} placeholder="Search categories or subcategories" aria-label="Search categories or subcategories" /></label>
      <div className="tag-category-scroll">
      {!searchText && frequent.length > 0 && <section className="frequent-categories"><small>Frequently used</small><div>{frequent.map((category) => <button className={selectedCategoryId === category.id ? "selected" : ""} key={category.id} onClick={() => onSelectCategory(category.id)}>{category.name}</button>)}</div></section>}
      <div className="tag-groups">{parents.map((parent) => {
        const allChildren = childrenByParent.get(parent.id) ?? [];
        const parentMatches = parent.name.toLocaleLowerCase().includes(searchText);
        const children = searchText && !parentMatches
          ? allChildren.filter((child) => child.name.toLocaleLowerCase().includes(searchText))
          : [...allChildren].sort((left, right) => Number(right.usage_count ?? 0) - Number(left.usage_count ?? 0) || left.name.localeCompare(right.name));
        return <section className={`tag-group ${selectedCategoryId === parent.id ? "selected" : ""}`} key={parent.id}><button className="tag-group-heading" onClick={() => onSelectCategory(parent.id)}><span className="radio" /> <span><strong>{parent.name}</strong><small>{categoryDescription(parent.code)}</small></span></button>{children.length > 0 && <div className="subcategory-grid">{children.map((child) => <button className={selectedSubcategoryId === child.id ? "subcategory selected" : "subcategory"} onClick={() => onSelectSubcategory(parent.id, child.id)} key={child.id}><CategoryIcon code={child.code} name={child.name} /><small>{child.name}</small></button>)}</div>}</section>;
      })}{parents.length === 0 && <p className="muted tag-empty">No matching category or subcategory.</p>}</div>
      </div>
    </section>
  </div>;
}
function ImportList({ imports, onOpen, onCancel }: { imports: ImportItem[]; onOpen: (id: string) => void; onCancel: (id: string) => void }) { if (!imports.length) return <p className="muted">No statement imports yet.</p>; return <div className="import-list">{imports.slice(0, 5).map((item) => <div key={item.id}><span><strong>{item.filename}</strong><small>{item.valid_row_count} valid rows · {new Date(item.created_at).toLocaleDateString()}</small></span><span className="import-action"><em className={`state ${item.state}`}>{item.state.replaceAll("_", " ")}</em><button className="secondary mini" onClick={() => onOpen(item.id)}>Open</button>{item.state === "preview_ready" && <button className="secondary mini" onClick={() => onCancel(item.id)}>Cancel</button>}</span></div>)}</div>; }
function PrivacyStat({ label, value }: { label: string; value: number }) { return <article><ShieldCheck size={20} /><span>{label}</span><strong>{value.toLocaleString("en-IN")}</strong></article>; }
function Detail({ label, value }: { label: string; value: string }) { return <p className="detail"><span>{label}</span><strong>{value}</strong></p>; }
function formatAmount(value?: string | null) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value ?? 0)); }
function balanceSourceLabel(account: AccountBalance) { if (account.balance_source === "unavailable") return "Confirm a recent statement to set balance"; if (account.balance_as_of) return `Statement verified · as of ${formatShortDate(account.balance_as_of)}`; return "Statement verified balance"; }
function formatFileSize(value: number | null) { if (value === null) return "Content deleted"; if (value < 1024) return `${value} B`; if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`; return `${(value / (1024 * 1024)).toFixed(1)} MB`; }
function greeting() { const hour = new Date().getHours(); const salutation = hour < 5 ? "Good night" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : hour < 22 ? "Good evening" : "Good night"; return <>{salutation},<span className="greeting-name">Aakash</span></>; }
function formatMonth(month: string) { return new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric" }).format(new Date(`${month}-01T00:00:00`)); }
function reportingPeriodLabel(period: ReportingPeriod) { return reportingPeriods.find(([value]) => value === period)?.[1] ?? "This month"; }
function formatShortDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(`${value}T00:00:00`)); }
function formatLongDate(value: string) { return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`)); }
function formatTrendPeriod(period: string, granularity: "monthly" | "yearly") { return granularity === "yearly" ? period : new Intl.DateTimeFormat("en-IN", { month: "short" }).format(new Date(`${period}-01T00:00:00`)); }
function categoryLabel(category: Category) { return category.parent_name ? `${category.parent_name} → ${category.name}` : category.name; }
function transactionCategoryLabel(transaction: Transaction, categories?: Category[]) {
  const category = categories?.find((item) => item.id === transaction.category_id);
  const subcategory = categories?.find((item) => item.id === transaction.subcategory_id);
  const parentName = category?.name ?? transaction.category;
  const subcategoryName = subcategory?.name ?? transaction.subcategory;
  return parentName && subcategoryName ? `${parentName} (${subcategoryName})` : parentName;
}
function categoryDescription(code: string) { return ({ food_drinks: "Dining, delivery, coffee, snacks and more", transport: "Rides, fuel, parking, travel and more", shopping: "Clothes, electronics, home and more", groceries: "Everyday food and household essentials", home: "Rent, repairs and home care", entertainment: "Movies, music, games and hobbies", events: "Tickets, gifts and celebrations", travel: "Hotels, bookings and foreign exchange", medical: "Healthcare, pharmacy and insurance", personal: "Personal care and everyday needs", fitness: "Gym, sports and wellness", services: "Professional, delivery and government", bills: "Utilities and recurring household bills", subscriptions: "Software, streaming and memberships", emi: "Loan instalments", credit_bill: "Credit-card bill payments" })[code] ?? "Choose a subcategory"; }
function CategoryIcon({ code, name }: { code: string; name: string }) {
  const icons: Record<string, LucideIcon> = {
    food_drinks_eating_out: Utensils, food_drinks_take_away: Package, food_drinks_tea_coffee: Coffee, food_drinks_fast_food: Utensils, food_drinks_snacks: Package, food_drinks_swiggy: Bike, food_drinks_zomato: Bike, food_drinks_sweets: Cake, food_drinks_liquor: Wine, food_drinks_beverages: Coffee, food_drinks_date: Users, food_drinks_pizza: Pizza, food_drinks_tiffin: Utensils,
    transport_uber: Car, transport_rapido: Bike, transport_auto: Car, transport_cab: Car, transport_train: TrainFront, transport_metro: TrainFront, transport_bus: BusFront, transport_bike: Bike, transport_fuel: Fuel, transport_ev_recharge: BatteryCharging, transport_flights: Plane, transport_parking: ParkingCircle, transport_fasttag: Ticket, transport_tolls: CircleDollarSign, transport_lounge: Users, transport_fine: CircleDollarSign,
    shopping_clothes: Shirt, shopping_footwear: Footprints, shopping_electronics: Monitor, shopping_festival: PartyPopper, shopping_video_games: Gamepad2, shopping_books: BookOpen, shopping_plants: Sprout, shopping_jewellery: Gem, shopping_furniture: Armchair, shopping_appliances: Package, shopping_utensils: Utensils, shopping_vehicle: Car, shopping_cosmetics: Sparkles, shopping_toys: ToyBrick, shopping_stationery: PenLine,
    groceries_supermarket: ShoppingBasket, groceries_fruits_vegetables: Apple, groceries_dairy: Milk, groceries_meat_seafood: Beef, groceries_household_supplies: Package,
    home_rent: House, home_maintenance: Wrench, home_repairs: Wrench, home_furnishing: Armchair, home_domestic_help: Users,
    entertainment_movies: Tv, entertainment_streaming: Monitor, entertainment_games: Gamepad2, entertainment_music: Music2, entertainment_hobbies: Sparkles,
    events_tickets: Ticket, events_celebrations: PartyPopper, events_gifts: Gift, events_conferences: Users,
    travel_hotels: Building2, travel_bookings: CalendarDays, travel_visa: Ticket, travel_foreign_exchange: CircleDollarSign,
    medical_doctor: Stethoscope, medical_pharmacy: Pill, medical_tests: TestTube, medical_hospital: Building2, medical_insurance: HeartPulse,
    personal_salon: Scissors, personal_clothing_care: Shirt, personal_mobile: Phone, personal_miscellaneous: MoreHorizontal,
    fitness_gym: Dumbbell, fitness_sports: Trophy, fitness_wellness: HeartPulse,
    services_professional: Briefcase, services_repairs: Wrench, services_delivery: Truck, services_government: Landmark,
    bills_electricity: Zap, bills_water: Droplets, bills_internet: Wifi, bills_mobile: Phone, bills_gas: Flame,
    subscriptions_software: Monitor, subscriptions_streaming: Tv, subscriptions_memberships: Users,
    emi_home_loan: House, emi_vehicle_loan: Car, emi_personal_loan: CircleDollarSign, credit_bill_credit_card_bill_payment: CreditCard,
  };
  const Icon = icons[code] ?? Package;
  return <span className="category-icon" aria-label={name} title={name}><Icon size={17} strokeWidth={1.9} /></span>;
}
function viewTitle(view: View) { return ({ transactions: "Transactions", spending: "Spending", budgets: "Budgets", recurring: "Recurring", accounts: "Accounts", cards: "Credit cards", imports: "Imports", notifications: "Notifications", mailboxes: "Mailboxes", privacy: "Privacy", home: "Home" })[view]; }
function viewSubtitle(view: View) { return ({ transactions: "Search, review, and categorise your ledger.", spending: "Understand where your money goes over time.", budgets: "Plan monthly category spending and track progress.", recurring: "Review recurring payments and subscription commitments.", accounts: "Your savings accounts and recorded balances.", cards: "Card activity is separate from your bank balance.", imports: "Review statement data before it reaches the ledger.", notifications: "Review scans, reminders, and actions that need you.", mailboxes: "Connect and manage your Gmail transaction sources.", privacy: "Export your data and control source-file retention.", home: "Your money, clearly organised." })[view]; }
function navIcon(view: View) { return ({ home: "⌂", transactions: "↔", spending: "◔", budgets: "◎", recurring: "↻", accounts: "⌑", cards: "▣", imports: "⇧", notifications: "♢", mailboxes: "✉", privacy: "◇" })[view]; }
