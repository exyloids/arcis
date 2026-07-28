"use client";

import { ChangeEvent, FormEvent, type ReactNode, useEffect, useState } from "react";
import { Apple, Armchair, BatteryCharging, Beef, Bike, BookOpen, Briefcase, Building2, BusFront, Cake, CalendarDays, Car, CircleDollarSign, Coffee, CreditCard, Droplets, Dumbbell, Flame, Footprints, Fuel, Gamepad2, Gem, Gift, HeartPulse, House, Landmark, Milk, Monitor, MoreHorizontal, Music2, Package, ParkingCircle, PartyPopper, PenLine, Phone, Pill, Pizza, Plane, Scissors, Shirt, ShoppingBasket, Sparkles, Sprout, Stethoscope, TestTube, Ticket, ToyBrick, TrainFront, Truck, Trophy, Tv, Users, Utensils, Wifi, Wine, Wrench, Zap, type LucideIcon } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const navigation = [
  ["home", "Home"], ["transactions", "Transactions"], ["accounts", "Accounts"],
  ["cards", "Cards"], ["imports", "Imports"], ["mailboxes", "Mailboxes"],
] as const;

type View = (typeof navigation)[number][0];
type Account = { id: string; display_name: string; institution_code: string; account_type: string };
type AccountBalance = Account & { balance: string; currency: string };
type Transaction = { id: string; transaction_date: string; narration: string; merchant_normalized?: string | null; provider_reference?: string | null; amount: string; currency: string; direction: string; account_name: string; category: string | null; category_id: string | null };
type Category = { id: string; code: string; name: string; parent_id?: string | null; parent_name?: string | null };
type TransactionPage = { items: Transaction[]; next_cursor: string | null };
type Preview = { import: { id: string; filename: string; row_count: number; valid_row_count: number; invalid_row_count: number; state: string }; rows: Transaction[]; errors: Array<{ ordinal: number; message: string }>; statement?: { parser_name: string; period_start: string | null; period_end: string | null; statement_amount: string | null; minimum_due: string | null; due_date: string | null } };
type Report = { income: string; expense: string; categories: Array<{ category: string; direction: string; amount: string }> };
type BalanceSummary = { cash_balance: string; credit_card_outstanding: string; net_worth: string; accounts: AccountBalance[] };
type ImportItem = { id: string; filename: string; state: string; row_count: number; valid_row_count: number; invalid_row_count: number; duplicate_count: number; created_at: string; confirmed_at: string | null };
type Inspection = { headers: string[]; suggested_mapping: Record<string, string>; sample_row_count: number };
type Mapping = Record<string, string>;
type Mailbox = { id: string; display_email: string; connection_status: string; history_cursor: string | null; last_successful_sync_at: string | null };
type Candidate = { id: string; parser_name: string; state: string; review_reason: string | null; financial_account_id: string | null; normalized: Record<string, string> };
type StatementAttachment = { id: string; mailbox_id: string | null; provider_message_id: string | null; byte_size: number; created_at: string };
type ReconciliationReview = { id: string; state: string; match_method: string; match_score: string; reason: string; ordinal: number; transaction_date: string; narration: string; amount: string; direction: string; candidate_narration: string | null; candidate_date: string | null };
type RecurringPayment = { id: string; display_name: string; account_name: string; category: string | null; cadence: string; typical_amount: string; next_expected_on: string; confidence: string; state: "detected" | "confirmed" | "dismissed" };
type MonthlyInsights = { month: string; expense: string; forecast: { projected_expense: string; days_observed: number; days_in_month: number } | null; anomalies: Array<{ kind: string; title: string; amount: string; category?: string; merchant?: string; reason: string }> };

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
  const [ledgerMonth, setLedgerMonth] = useState(new Date().toISOString().slice(0, 7));
  const [ledgerAccountType, setLedgerAccountType] = useState<"bank_account" | "credit_card">("bank_account");
  const [search, setSearch] = useState("");
  const [showLedgerFilters, setShowLedgerFilters] = useState(false);
  const [showMonthPicker, setShowMonthPicker] = useState(false);
  const [evidence, setEvidence] = useState<Array<Record<string, string>> | null>(null);
  const [selectedTransaction, setSelectedTransaction] = useState<Transaction | null>(null);
  const [showTransactionMoreDetails, setShowTransactionMoreDetails] = useState(false);
  const [taggingTransaction, setTaggingTransaction] = useState<Transaction | null>(null);
  const [tagCategoryId, setTagCategoryId] = useState("");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [statementAttachments, setStatementAttachments] = useState<StatementAttachment[]>([]);
  const [reconciliationReviews, setReconciliationReviews] = useState<ReconciliationReview[]>([]);
  const [recurringPayments, setRecurringPayments] = useState<RecurringPayment[]>([]);
  const [monthlyInsights, setMonthlyInsights] = useState<MonthlyInsights | null>(null);
  const [attachmentAccountId, setAttachmentAccountId] = useState("");
  const [attachmentPassword, setAttachmentPassword] = useState("");
  const [backfillMailboxId, setBackfillMailboxId] = useState("");
  const [backfillQuery, setBackfillQuery] = useState("from:(alerts@alerts.icicibank.com OR alerts@alerts.hdfcbank.com) newer_than:365d");
  const currentMonth = new Date().toISOString().slice(0, 7);
  const bankAccounts = balanceSummary?.accounts.filter((account) => account.account_type === "bank_account") ?? [];
  const creditCards = balanceSummary?.accounts.filter((account) => account.account_type === "credit_card") ?? [];

  async function loadLedger() {
    const ledgerParams = new URLSearchParams();
    if (ledgerMonth) ledgerParams.set("month", ledgerMonth);
    ledgerParams.set("account_type", ledgerAccountType);
    if (ledgerAccountId) ledgerParams.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) ledgerParams.set("category_id", ledgerCategoryId);
    if (search.trim()) ledgerParams.set("q", search.trim());
    const page = await request<TransactionPage>(`/api/v1/transactions/page?${ledgerParams}`);
    setTransactions(page.items); setNextCursor(page.next_cursor);
  }

  async function refresh() {
    const ledgerParams = new URLSearchParams();
    if (ledgerMonth) ledgerParams.set("month", ledgerMonth);
    ledgerParams.set("account_type", ledgerAccountType);
    if (ledgerAccountId) ledgerParams.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) ledgerParams.set("category_id", ledgerCategoryId);
    if (search.trim()) ledgerParams.set("q", search.trim());
    const [nextAccounts, nextCategories, transactionPage, nextReport, nextBalanceSummary, nextImports, nextMailboxes, nextCandidates, nextAttachments, nextReviews, nextRecurringPayments, nextMonthlyInsights] = await Promise.all([
      request<Account[]>("/api/v1/financial-accounts"), request<Category[]>("/api/v1/categories"),
      request<TransactionPage>(`/api/v1/transactions/page?${ledgerParams}`), request<Report>(`/api/v1/reports/monthly?month=${currentMonth}`),
      request<BalanceSummary>("/api/v1/accounts/balance-summary"), request<ImportItem[]>("/api/v1/imports"),
      request<Mailbox[]>("/api/v1/mailboxes"), request<Candidate[]>("/api/v1/parser-candidates"),
      request<StatementAttachment[]>("/api/v1/statement-attachments"), request<ReconciliationReview[]>("/api/v1/reconciliation-reviews"),
      request<RecurringPayment[]>("/api/v1/recurring-payments?state=detected"),
      request<MonthlyInsights>(`/api/v1/insights/monthly?month=${currentMonth}`),
    ]);
    setAccounts(nextAccounts); setCategories(nextCategories); setTransactions(transactionPage.items); setNextCursor(transactionPage.next_cursor);
    setReport(nextReport); setBalanceSummary(nextBalanceSummary); setImports(nextImports); setMailboxes(nextMailboxes);
    setCandidates(nextCandidates); setStatementAttachments(nextAttachments); setReconciliationReviews(nextReviews);
    setRecurringPayments(nextRecurringPayments);
    setMonthlyInsights(nextMonthlyInsights);
    if (!accountId && nextAccounts[0]) setAccountId(nextAccounts[0].id);
    if (!attachmentAccountId && nextAccounts[0]) setAttachmentAccountId(nextAccounts[0].id);
    if (!backfillMailboxId && nextMailboxes[0]) setBackfillMailboxId(nextMailboxes[0].id);
  }

  useEffect(() => { void refresh().catch((error: Error) => setMessage(error.message)); }, []);
  useEffect(() => {
    if (activeView !== "transactions") return;
    const timer = window.setTimeout(() => { void loadLedger().catch((error: Error) => setMessage(error.message)); }, 160);
    return () => window.clearTimeout(timer);
  }, [activeView, ledgerAccountType, ledgerAccountId, ledgerCategoryId, ledgerMonth, search]);

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const formElement = event.currentTarget;
    try { await request("/api/v1/financial-accounts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(formElement))) }); formElement.reset(); setMessage("Account created."); await refresh(); }
    catch (error) { setMessage((error as Error).message); }
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
  async function confirmImport() {
    if (!preview) return;
    try { const result = await request<{ created: number; duplicates?: number; matched?: number; uncertain?: number; categorized?: number }>(`/api/v1/imports/${preview.import.id}/confirm`, { method: "POST" }); const categorization = result.categorized ? ` ${result.categorized} transaction(s) categorized.` : ""; setMessage(preview.statement ? `Statement confirmed: ${result.created} statement-only transactions, ${result.matched ?? 0} matched, ${result.uncertain ?? 0} need review.${categorization}` : `Import confirmed: ${result.created} transactions created, ${result.duplicates ?? 0} duplicates ignored.${categorization}`); setPreview(null); setFile(null); await refresh(); }
    catch (error) { setMessage((error as Error).message); }
  }
  async function cancelImport(importId: string) { try { await request<void>(`/api/v1/imports/${importId}/cancel`, { method: "POST" }); if (preview?.import.id === importId) setPreview(null); setMessage("Import cancelled and its staged document removed."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function openImport(importId: string) { try { setPreview(await request<Preview>(`/api/v1/imports/${importId}/preview`)); setActiveView("imports"); setMessage("Viewing stored import preview."); } catch (error) { setMessage((error as Error).message); } }
  async function updateCategory(transactionId: string, categoryId: string, rememberMerchant = false) { try { await request(`/api/v1/transactions/${transactionId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category_id: categoryId || null, remember_merchant: rememberMerchant }) }); setMessage("Transaction category updated."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function showEvidence(transactionId: string) { try { setEvidence(await request<Array<Record<string, string>>>(`/api/v1/transactions/${transactionId}/evidence`)); } catch (error) { setMessage((error as Error).message); } }
  async function categorizeTransactions() { try { const result = await request<{ rules: number; transactions_updated: number }>("/api/v1/categories/categorize", { method: "POST" }); setMessage(`${result.transactions_updated} transactions categorized using ${result.rules} deterministic rules.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function loadMore() { if (!nextCursor) return; const params = new URLSearchParams({ cursor: nextCursor }); if (ledgerMonth) params.set("month", ledgerMonth); params.set("account_type", ledgerAccountType); if (ledgerAccountId) params.set("account_id", ledgerAccountId); if (ledgerCategoryId) params.set("category_id", ledgerCategoryId); if (search.trim()) params.set("q", search.trim()); try { const page = await request<TransactionPage>(`/api/v1/transactions/page?${params}`); setTransactions([...transactions, ...page.items]); setNextCursor(page.next_cursor); } catch (error) { setMessage((error as Error).message); } }
  async function syncMailbox(mailboxId: string) { try { const job = await request<{ id: string }>(`/api/v1/mailboxes/${mailboxId}/sync`, { method: "POST" }); setMessage(`Sync queued: ${job.id}`); } catch (error) { setMessage((error as Error).message); } }
  async function reviewCandidate(id: string, state: "accepted" | "rejected") { try { await request(`/api/v1/parser-candidates/${id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state }) }); setMessage(`Candidate ${state}.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function assignCandidateAccount(candidateId: string, financialAccountId: string) { if (!financialAccountId) return setMessage("Select an account first."); try { await request(`/api/v1/parser-candidates/${candidateId}/account`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ financial_account_id: financialAccountId }) }); setMessage("Candidate account assigned. You can now accept it."); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function backfillMailbox(event: FormEvent<HTMLFormElement>) { event.preventDefault(); try { const result = await request<{ scanned: number; added: number; duplicates: number }>(`/api/v1/mailboxes/${backfillMailboxId}/backfill`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: backfillQuery, max_results: 500 }) }); setMessage(`Backfill complete: ${result.scanned} scanned, ${result.added} added, ${result.duplicates} duplicates.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function previewStatementAttachment(artifactId: string) { if (!attachmentAccountId) return setMessage("Select the account that owns this statement."); try { const result = await request<Preview>(`/api/v1/statement-attachments/${artifactId}/preview?account_id=${attachmentAccountId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pdf_password: attachmentPassword }) }); setPreview(result); setAttachmentPassword(""); setActiveView("imports"); setMessage("Statement attachment parsed. Review it before confirmation."); } catch (error) { setMessage((error as Error).message); } }
  async function resolveReconciliation(reviewId: string, state: "accepted" | "rejected") { try { await request(`/api/v1/reconciliation-reviews/${reviewId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state }) }); setMessage(`Reconciliation ${state}.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function detectRecurringPayments() { try { const result = await request<{ detected: number }>("/api/v1/recurring-payments/detect", { method: "POST" }); setMessage(`${result.detected} recurring payment pattern(s) found for review.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  async function reviewRecurringPayment(id: string, state: "confirmed" | "dismissed") { try { await request(`/api/v1/recurring-payments/${id}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ state }) }); setMessage(`Recurring payment ${state}.`); await refresh(); } catch (error) { setMessage((error as Error).message); } }
  function openTransactions(type: "bank_account" | "credit_card", selectedAccountId = "") { setLedgerAccountType(type); setLedgerAccountId(selectedAccountId); setActiveView("transactions"); }
  function openTransactionDetails(transaction: Transaction) { setSelectedTransaction(transaction); setShowTransactionMoreDetails(false); }

  return <main className="app-shell">
    <aside className="sidebar"><button className="brand" onClick={() => setActiveView("home")} aria-label="Go to home"><span>₹</span>Arcis</button><nav>{navigation.map(([view, label]) => <button key={view} className={activeView === view ? "nav-item active" : "nav-item"} onClick={() => setActiveView(view)}>{navIcon(view)}<span>{label}</span></button>)}</nav><div className="sidebar-note"><span className="status-dot" />Private ledger<br /><small>Read-only financial tracking</small></div></aside>
    <div className="main-content">
      <header className="topbar"><div><p className="eyebrow">ARCIS FINANCE</p><h1>{activeView === "home" ? greeting() : viewTitle(activeView)}</h1><p className="subtitle">{activeView === "home" ? "Your money, clearly organised." : viewSubtitle(activeView)}</p></div><div className="top-actions"><button className="icon-button" onClick={() => void refresh()} aria-label="Refresh data">↻</button><button className="profile" onClick={() => setActiveView("mailboxes")} aria-label="Open mailbox settings">A</button></div></header>
      <nav className="mobile-nav" aria-label="Primary navigation">{navigation.map(([view, label]) => <button key={view} className={activeView === view ? "active" : ""} onClick={() => setActiveView(view)}>{navIcon(view)}<span>{label}</span></button>)}</nav>
      {message && <p className="notice" role="status">{message}</p>}

      {activeView === "home" && <>
        <section className="hero-balance"><div><span className="section-kicker">Total bank balance</span><strong>{formatAmount(balanceSummary?.cash_balance)}</strong><p>Savings accounts only · cards tracked separately</p></div><button className="text-action" onClick={() => openTransactions("bank_account")}>View transactions →</button></section>
        <section className="summary-grid"><SummaryCard icon="↗" label="Incoming" value={formatAmount(report?.income)} tone="positive" /><SummaryCard icon="↘" label="Outgoing" value={formatAmount(report?.expense)} tone="negative" /><SummaryCard icon="▣" label="Card outstanding" value={formatAmount(balanceSummary?.credit_card_outstanding)} action={() => setActiveView("cards")} /></section>
        <section className="dashboard-grid">
          <DashboardCard title="Spending summary" action="All transactions" onAction={() => openTransactions("bank_account")}><p className="month-label">{formatMonth(currentMonth)}</p><CategoryBars categories={report?.categories ?? []} /></DashboardCard>
          <DashboardCard title="Recent transactions" action="View all" onAction={() => openTransactions("bank_account")}><TransactionList transactions={transactions.slice(0, 5)} onOpen={openTransactionDetails} compact /></DashboardCard>
          <DashboardCard title="Bank accounts" action="Manage" onAction={() => setActiveView("accounts")}><AccountList accounts={bankAccounts} empty="Add a savings account to start tracking cash." onOpen={(id) => openTransactions("bank_account", id)} /></DashboardCard>
          <DashboardCard title="Credit cards" action="View cards" onAction={() => setActiveView("cards")}><AccountList accounts={creditCards} empty="Add a credit card to track card spending separately." onOpen={(id) => openTransactions("credit_card", id)} card /></DashboardCard>
          <DashboardCard title="Upcoming recurring payments" action="Scan" onAction={() => void detectRecurringPayments()}><RecurringPaymentList payments={recurringPayments} onReview={reviewRecurringPayment} /></DashboardCard>
          <DashboardCard title="Monthly insights"><MonthlyInsightsCard insights={monthlyInsights} /></DashboardCard>
          <DashboardCard title="Mailbox sync" action="Manage" onAction={() => setActiveView("mailboxes")}><p className="sync-copy"><span className={mailboxes.some((mailbox) => mailbox.connection_status === "connected") ? "status-dot" : "status-dot offline"} />{mailboxes.filter((mailbox) => mailbox.connection_status === "connected").length} connected mailbox{mailboxes.filter((mailbox) => mailbox.connection_status === "connected").length === 1 ? "" : "es"}</p><p className="muted">Connect Gmail to bring transaction alerts and statements into Arcis.</p></DashboardCard>
        </section>
      </>}

      {activeView === "transactions" && <section className="page-section transaction-page"><div className="segmented transaction-tabs" aria-label="Transaction source"><button className={ledgerAccountType === "bank_account" ? "active" : ""} onClick={() => { setLedgerAccountType("bank_account"); setLedgerAccountId(""); }}>Savings accounts</button><button className={ledgerAccountType === "credit_card" ? "active" : ""} onClick={() => { setLedgerAccountType("credit_card"); setLedgerAccountId(""); }}>Credit cards</button></div><div className="ledger-toolbar"><div className="ledger-popover-wrap"><button className="secondary toolbar-button period-button" onClick={() => setShowMonthPicker(!showMonthPicker)}>▣ <span>{formatMonth(ledgerMonth)}</span></button>{showMonthPicker && <div className="ledger-popover month-popover"><label>Month<select value={ledgerMonth.slice(5)} onChange={(event) => setLedgerMonth(`${ledgerMonth.slice(0, 4)}-${event.target.value}`)}>{Array.from({ length: 12 }, (_, index) => <option key={index} value={String(index + 1).padStart(2, "0")}>{new Intl.DateTimeFormat("en-IN", { month: "long" }).format(new Date(2026, index, 1))}</option>)}</select></label><label>Year<select value={ledgerMonth.slice(0, 4)} onChange={(event) => setLedgerMonth(`${event.target.value}-${ledgerMonth.slice(5)}`)}>{Array.from({ length: 7 }, (_, index) => String(new Date().getFullYear() - index)).map((year) => <option key={year}>{year}</option>)}</select></label></div>}</div><input className="ledger-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" aria-label="Search transactions" /><div className="ledger-popover-wrap"><button className={ledgerAccountId || ledgerCategoryId ? "secondary toolbar-button active-filter" : "secondary toolbar-button"} onClick={() => setShowLedgerFilters(!showLedgerFilters)} aria-label="Filter transactions"><FilterIcon /></button>{showLedgerFilters && <div className="ledger-popover filter-popover"><label>Account<select value={ledgerAccountId} onChange={(event) => setLedgerAccountId(event.target.value)}><option value="">All accounts</option>{accounts.filter((account) => account.account_type === ledgerAccountType).map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select></label><label>Category<select value={ledgerCategoryId} onChange={(event) => setLedgerCategoryId(event.target.value)}><option value="">All categories</option>{categories.filter((category) => !category.parent_id).map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><button className="secondary clear-filters" onClick={() => { setLedgerAccountId(""); setLedgerCategoryId(""); setShowLedgerFilters(false); }}>All</button></div>}</div></div><TransactionList transactions={transactions} categories={categories} onOpen={openTransactionDetails} onTag={(transaction) => { setTaggingTransaction(transaction); setTagCategoryId(transaction.category_id ?? ""); }} />{nextCursor && <button className="secondary load-more" onClick={() => void loadMore()}>Load more</button>}</section>}

      {activeView === "accounts" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">SAVINGS</p><h2>Bank accounts</h2></div></div><div className="account-layout"><DashboardCard title="Your accounts"><AccountList accounts={bankAccounts} empty="No bank accounts added yet." onOpen={(id) => openTransactions("bank_account", id)} /></DashboardCard><form className="form-card" onSubmit={createAccount}><h3>Add account</h3><input name="display_name" placeholder="Display name" required /><input name="institution_code" placeholder="Institution, e.g. icici" required /><input name="product_name" placeholder="Product name" required /><input name="masked_identifier" placeholder="Masked identifier, e.g. XX1234" /><select name="account_type" defaultValue="bank_account"><option value="bank_account">Bank account</option><option value="credit_card">Credit card</option></select><input name="currency" defaultValue="INR" required /><button type="submit">Create account</button></form></div></section>}

      {activeView === "cards" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">CARD SPENDING</p><h2>Credit cards</h2></div><span className="headline-amount">{formatAmount(balanceSummary?.credit_card_outstanding)}</span></div><p className="muted page-note">Credit-card purchases are tracked here and do not change your total bank balance.</p><div className="account-layout"><DashboardCard title="Outstanding by card"><AccountList accounts={creditCards} empty="No credit cards added yet." onOpen={(id) => openTransactions("credit_card", id)} card /></DashboardCard><DashboardCard title="Card payments"><p className="muted">Card bill payments are visible in savings-account transactions as a dedicated category.</p><button onClick={() => openTransactions("bank_account")}>View savings ledger</button></DashboardCard></div></section>}

      {activeView === "imports" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">STATEMENTS</p><h2>Imports & reconciliation</h2></div></div><div className="account-layout"><form className="form-card" onSubmit={inspectFile}><h3>Import statement</h3><select value={accountId} onChange={(event) => setAccountId(event.target.value)} required><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select><input type="file" accept=".csv,.xlsx,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required />{file?.name.toLowerCase().endsWith(".pdf") && <input type="password" value={pdfPassword} onChange={(event) => setPdfPassword(event.target.value)} placeholder="PDF password, if required" />}<p className="hint">CSV, XLSX, or PDF · password is used only for this preview</p><button type="submit">Inspect statement</button></form><DashboardCard title="Import history"><ImportList imports={imports} onOpen={openImport} onCancel={cancelImport} /></DashboardCard></div>{inspection && <section className="panel"><h3>Column mapping · {file?.name}</h3><p className="muted">Review the detected columns before parsing the statement.</p><div className="mapping-grid">{mappingFields.map(([field, label, required]) => <label key={field}>{label}{required ? " *" : ""}<select value={mapping[field] ?? ""} onChange={(event) => setMapping({ ...mapping, [field]: event.target.value })}><option value="">{required ? "Select column" : "Not available"}</option>{inspection.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select></label>)}</div><button onClick={() => void createPreview()}>Create preview</button></section>}{preview && <section className="panel"><h3>Import preview · {preview.import.filename}</h3><p className="muted">{preview.import.valid_row_count} valid and {preview.import.invalid_row_count} invalid rows from {preview.import.row_count} source rows.</p>{preview.statement && <p className="hint">Parser: {preview.statement.parser_name} · Statement amount: {formatAmount(preview.statement.statement_amount)} · Minimum due: {formatAmount(preview.statement.minimum_due)} · Due: {preview.statement.due_date ?? "—"}</p>}{preview.errors.length > 0 && <div className="import-errors"><h4>Rows needing review</h4><ul>{preview.errors.map((error) => <li key={error.ordinal}>Row {error.ordinal}: {error.message}</li>)}</ul></div>}<TransactionList transactions={preview.rows} />{preview.import.state === "preview_ready" && <button onClick={confirmImport}>Confirm valid rows</button>}</section>}<section className="panel"><h3>Statement reconciliation review</h3>{reconciliationReviews.length ? <div className="table-wrap"><table><thead><tr><th>Statement row</th><th>Ledger candidate</th><th>Match</th><th>Decision</th></tr></thead><tbody>{reconciliationReviews.map((review) => <tr key={review.id}><td>{review.transaction_date} · {review.narration} · {formatAmount(review.amount)}</td><td>{review.candidate_date ?? "—"} · {review.candidate_narration ?? "No candidate"}</td><td>{review.match_method} ({review.match_score})</td><td><button className="secondary" onClick={() => void resolveReconciliation(review.id, "accepted")}>Accept</button> <button className="secondary" onClick={() => void resolveReconciliation(review.id, "rejected")}>Reject</button></td></tr>)}</tbody></table></div> : <p className="muted">No uncertain statement matches need a decision.</p>}</section></section>}

      {activeView === "mailboxes" && <section className="page-section"><div className="section-heading"><div><p className="section-kicker">GMAIL</p><h2>Mailboxes</h2></div><a className="button-link" href={`${API_URL}/api/v1/oauth/gmail/start`}>Connect Gmail</a></div><section className="panel"><h3>Connected mailboxes</h3>{mailboxes.length ? <><div className="table-wrap"><table><thead><tr><th>Mailbox</th><th>Status</th><th>Last sync</th><th /></tr></thead><tbody>{mailboxes.map((mailbox) => <tr key={mailbox.id}><td>{mailbox.display_email}</td><td><span className="status-chip">{mailbox.connection_status}</span></td><td>{mailbox.last_successful_sync_at ? new Date(mailbox.last_successful_sync_at).toLocaleString() : "Not yet synced"}</td><td><button className="secondary" onClick={() => void syncMailbox(mailbox.id)}>Sync now</button></td></tr>)}</tbody></table></div><form className="backfill" onSubmit={backfillMailbox}><h3>Historical bank-email import</h3><select value={backfillMailboxId} onChange={(event) => setBackfillMailboxId(event.target.value)}>{mailboxes.map((mailbox) => <option key={mailbox.id} value={mailbox.id}>{mailbox.display_email}</option>)}</select><input value={backfillQuery} onChange={(event) => setBackfillQuery(event.target.value)} aria-label="Gmail backfill query" /><button type="submit">Backfill matching emails</button></form></> : <p className="muted">Connect a Gmail mailbox to begin.</p>}</section><section className="panel"><h3>Statement attachments</h3>{statementAttachments.length ? <><div className="attachment-controls"><select value={attachmentAccountId} onChange={(event) => setAttachmentAccountId(event.target.value)}><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select><input type="password" value={attachmentPassword} onChange={(event) => setAttachmentPassword(event.target.value)} placeholder="PDF password, if required" /></div><div className="table-wrap"><table><thead><tr><th>Received</th><th>Size</th><th /></tr></thead><tbody>{statementAttachments.map((attachment) => <tr key={attachment.id}><td>{new Date(attachment.created_at).toLocaleString()}</td><td>{Math.ceil(attachment.byte_size / 1024)} KB</td><td><button className="secondary" onClick={() => void previewStatementAttachment(attachment.id)}>Create preview</button></td></tr>)}</tbody></table></div></> : <p className="muted">No PDF statement attachments have been found yet.</p>}</section><section className="panel"><h3>Email parser review</h3>{candidates.length ? <div className="table-wrap"><table><thead><tr><th>Parser</th><th>Merchant</th><th>Amount</th><th>Status</th><th>Account and review</th></tr></thead><tbody>{candidates.map((candidate) => { const accountType = candidate.normalized.financial_account_hint?.startsWith("credit_card_") ? "credit_card" : "bank_account"; const eligibleAccounts = accounts.filter((account) => account.account_type === accountType); const actionable = ["ready", "needs_review"].includes(candidate.state); return <tr key={candidate.id}><td>{candidate.parser_name}</td><td>{candidate.normalized.merchant ?? candidate.review_reason ?? "Unsupported"}</td><td>{candidate.normalized.amount ?? "—"}</td><td>{candidate.state}</td><td>{actionable && <><select value={candidate.financial_account_id ?? ""} onChange={(event) => void assignCandidateAccount(candidate.id, event.target.value)} aria-label="Assign account"><option value="">Select {accountType.replace("_", " ")}</option>{eligibleAccounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select>{candidate.state === "ready" && <button className="secondary" onClick={() => void reviewCandidate(candidate.id, "accepted")}>Accept</button>} <button className="secondary" onClick={() => void reviewCandidate(candidate.id, "rejected")}>Reject</button></>}{candidate.state === "unsupported" && <button className="secondary" onClick={() => void reviewCandidate(candidate.id, "rejected")}>Reject</button>}</td></tr>; })}</tbody></table></div> : <p className="muted">No parsed Gmail messages awaiting review.</p>}</section></section>}

      {selectedTransaction && <div className="detail-backdrop"><section className="detail-sheet"><div className="detail-heading"><button className="icon-button" onClick={() => setSelectedTransaction(null)} aria-label="Close transaction details">×</button><p className="section-kicker">TRANSACTION</p><span /></div><div className="transaction-overview"><span className={selectedTransaction.direction === "credit" ? "amount credit" : "amount debit"}>{selectedTransaction.direction === "credit" ? "+" : "−"}{formatAmount(selectedTransaction.amount)}</span><button className="category-pill" onClick={() => { setTaggingTransaction(selectedTransaction); setTagCategoryId(selectedTransaction.category_id ?? ""); }}>{transactionCategoryLabel(selectedTransaction, categories) ?? "Tag transaction"}</button></div><div className="transaction-summary"><Detail label="From" value={selectedTransaction.account_name} /><Detail label="On" value={formatLongDate(selectedTransaction.transaction_date)} /><button className="paid-to" onClick={() => { setTaggingTransaction(selectedTransaction); setTagCategoryId(selectedTransaction.category_id ?? ""); }}><span>Paid to</span><strong>{selectedTransaction.merchant_normalized ?? selectedTransaction.narration}</strong><b>›</b></button></div><div className="detail-rows"><button className="detail-row" onClick={() => setShowTransactionMoreDetails(!showTransactionMoreDetails)}><span>More details</span><b>{showTransactionMoreDetails ? "⌃" : "›"}</b></button>{showTransactionMoreDetails && <div className="expanded-details"><Detail label="Summary" value={`${selectedTransaction.direction === "credit" ? "Received from" : "Paid to"} ${selectedTransaction.merchant_normalized ?? selectedTransaction.narration} on ${formatLongDate(selectedTransaction.transaction_date)}`} /><Detail label="Transaction type" value={selectedTransaction.direction === "credit" ? "Incoming" : "Outgoing"} /><Detail label="Narration" value={selectedTransaction.narration} /><Detail label="Transaction ID" value={selectedTransaction.id} /><Detail label="Transaction date" value={selectedTransaction.transaction_date} /><Detail label="Reference / UTR" value={selectedTransaction.provider_reference ?? "Not available"} /><button className="text-action evidence-action" onClick={() => void showEvidence(selectedTransaction.id)}>View source evidence</button></div>}</div></section></div>}
      {taggingTransaction && <TagTransactionSheet transaction={taggingTransaction} categories={categories} selectedCategoryId={tagCategoryId} onSelect={setTagCategoryId} onClose={() => setTaggingTransaction(null)} onSave={() => { void updateCategory(taggingTransaction.id, tagCategoryId, true); setSelectedTransaction({ ...taggingTransaction, category_id: tagCategoryId || null }); setTaggingTransaction(null); }} />}
      {evidence && <section className="detail-sheet"><div className="detail-heading"><h2>Transaction evidence</h2><button className="icon-button" onClick={() => setEvidence(null)} aria-label="Close evidence">×</button></div>{evidence.length ? <pre>{JSON.stringify(evidence, null, 2)}</pre> : <p className="muted">No source evidence found.</p>}</section>}
    </div>
  </main>;
}

function SummaryCard({ icon, label, value, tone, action }: { icon: string; label: string; value: string; tone?: string; action?: () => void }) { return <button className={`summary-card ${tone ?? ""}`} onClick={action}><span>{icon}</span><small>{label}</small><strong>{value}</strong></button>; }
function DashboardCard({ title, action, onAction, children }: { title: string; action?: string; onAction?: () => void; children: ReactNode }) { return <section className="dashboard-card"><div className="card-heading"><h3>{title}</h3>{action && <button className="text-action" onClick={onAction}>{action} →</button>}</div>{children}</section>; }
function MonthlyInsightsCard({ insights }: { insights: MonthlyInsights | null }) { if (!insights?.forecast) return <p className="muted">Add this month’s transactions to see a forecast and evidence-linked anomalies.</p>; return <div className="insights-card"><p><span>Projected month-end spend</span><strong>{formatAmount(insights.forecast.projected_expense)}</strong><small>Based on {insights.forecast.days_observed} of {insights.forecast.days_in_month} days observed.</small></p>{insights.anomalies.length ? <div className="insight-list">{insights.anomalies.slice(0, 3).map((insight, index) => <article key={`${insight.kind}-${index}`}><strong>{insight.title}</strong><span>{insight.reason}</span></article>)}</div> : <p className="muted">No unusual spending patterns were found for this month.</p>}</div>; }

function RecurringPaymentList({ payments, onReview }: { payments: RecurringPayment[]; onReview: (id: string, state: "confirmed" | "dismissed") => void }) { if (!payments.length) return <p className="muted">No recurring patterns found yet. Scan after you have a few months of history.</p>; return <div className="recurring-list">{payments.slice(0, 4).map((payment) => <article key={payment.id}><span><strong>{payment.display_name}</strong><small>{payment.cadence} · expected {formatShortDate(payment.next_expected_on)} · {payment.account_name}</small></span><b>{formatAmount(payment.typical_amount)}</b><span className="recurring-actions"><button className="secondary mini" onClick={() => onReview(payment.id, "confirmed")}>Confirm</button><button className="secondary mini" onClick={() => onReview(payment.id, "dismissed")}>Dismiss</button></span></article>)}</div>; }

function AccountList({ accounts, empty, onOpen, card = false }: { accounts: AccountBalance[]; empty: string; onOpen: (id: string) => void; card?: boolean }) { if (!accounts.length) return <p className="muted">{empty}</p>; return <div className="account-list">{accounts.map((account) => <button key={account.id} className="account-row" onClick={() => onOpen(account.id)}><span className={`account-mark ${card ? "card" : ""}`}><BankMark institutionCode={account.institution_code} fallback={card ? "▣" : "₹"} /></span><span><strong>{account.display_name}</strong><small>{card ? "Card outstanding" : "Recorded balance"}</small></span><b className={card ? "card-balance" : ""}>{formatAmount(card ? String(Math.abs(Number(account.balance))) : account.balance)}</b></button>)}</div>; }

function FilterIcon() { return <svg className="filter-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="11" cy="18" r="2" /></svg>; }

function BankMark({ institutionCode, fallback }: { institutionCode?: string; fallback: string }) {
  const code = institutionCode?.toLowerCase();
  const logo = code === "hdfc" ? { src: "https://upload.wikimedia.org/wikipedia/commons/2/28/HDFC_Bank_Logo.svg", alt: "HDFC Bank" } : code === "icici" ? { src: "https://upload.wikimedia.org/wikipedia/commons/1/12/ICICI_Bank_Logo.svg", alt: "ICICI Bank" } : null;
  return logo ? <img className={`bank-mark-logo ${code}`} src={logo.src} alt={logo.alt} /> : <span className="bank-mark-fallback">{fallback}</span>;
}
function CategoryBars({ categories }: { categories: Report["categories"] }) { const debits = categories.filter((category) => category.direction !== "credit").slice(0, 5); const largest = Math.max(...debits.map((category) => Number(category.amount)), 1); if (!debits.length) return <p className="muted">No categorized spending for this month yet.</p>; return <div className="category-bars">{debits.map((category) => <div key={category.category} className="category-bar"><div><span>{category.category}</span><b>{formatAmount(category.amount)}</b></div><i><em style={{ width: `${Math.max(7, (Number(category.amount) / largest) * 100)}%` }} /></i></div>)}</div>; }
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
function TagTransactionSheet({ transaction, categories, selectedCategoryId, onSelect, onClose, onSave }: { transaction: Transaction; categories: Category[]; selectedCategoryId: string; onSelect: (id: string) => void; onClose: () => void; onSave: () => void }) {
  const parents = categories.filter((category) => !category.parent_id);
  return <div className="tag-backdrop" role="dialog" aria-modal="true" aria-label="Tag transaction">
    <section className="tag-sheet"><header className="tag-header"><button className="tag-close" onClick={onClose} aria-label="Close tagging">×</button><h2>Tag transaction</h2><button className="tag-save" onClick={onSave} disabled={!selectedCategoryId} aria-label="Save category">✓</button></header>
      <article className="tag-transaction"><div><span className="transaction-icon">✎</span><strong>{transaction.merchant_normalized ?? transaction.narration}</strong></div><time>{formatShortDate(transaction.transaction_date)}</time><b className={transaction.direction === "credit" ? "credit" : "debit"}>{transaction.direction === "credit" ? "+" : "−"}{formatAmount(transaction.amount)}</b><p>Narration: {transaction.narration}</p></article>
      <div className="tag-search">⌕ <span>Choose a category</span></div>
      <div className="tag-groups">{parents.map((parent) => { const children = categories.filter((category) => category.parent_id === parent.id); return <section className={`tag-group ${selectedCategoryId === parent.id ? "selected" : ""}`} key={parent.id}><button className="tag-group-heading" onClick={() => onSelect(parent.id)}><span className="radio" /> <span><strong>{parent.name}</strong><small>{categoryDescription(parent.code)}</small></span></button>{children.length > 0 && <div className="subcategory-grid">{children.map((child) => <button className={selectedCategoryId === child.id ? "subcategory selected" : "subcategory"} onClick={() => onSelect(child.id)} key={child.id}><CategoryIcon code={child.code} name={child.name} /><small>{child.name}</small></button>)}</div>}</section>; })}</div>
    </section>
  </div>;
}
function ImportList({ imports, onOpen, onCancel }: { imports: ImportItem[]; onOpen: (id: string) => void; onCancel: (id: string) => void }) { if (!imports.length) return <p className="muted">No statement imports yet.</p>; return <div className="import-list">{imports.slice(0, 5).map((item) => <div key={item.id}><span><strong>{item.filename}</strong><small>{item.valid_row_count} valid rows · {new Date(item.created_at).toLocaleDateString()}</small></span><span className="import-action"><em className={`state ${item.state}`}>{item.state.replaceAll("_", " ")}</em><button className="secondary mini" onClick={() => onOpen(item.id)}>Open</button>{item.state === "preview_ready" && <button className="secondary mini" onClick={() => onCancel(item.id)}>Cancel</button>}</span></div>)}</div>; }
function Detail({ label, value }: { label: string; value: string }) { return <p className="detail"><span>{label}</span><strong>{value}</strong></p>; }
function formatAmount(value?: string | null) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value ?? 0)); }
function greeting() { const hour = new Date().getHours(); const salutation = hour < 5 ? "Good night" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : hour < 22 ? "Good evening" : "Good night"; return <>{salutation},<span className="greeting-name">Aakash</span></>; }
function formatMonth(month: string) { return new Intl.DateTimeFormat("en-IN", { month: "long", year: "numeric" }).format(new Date(`${month}-01T00:00:00`)); }
function formatShortDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short" }).format(new Date(`${value}T00:00:00`)); }
function formatLongDate(value: string) { return new Intl.DateTimeFormat("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`)); }
function categoryLabel(category: Category) { return category.parent_name ? `${category.parent_name} → ${category.name}` : category.name; }
function transactionCategoryLabel(transaction: Transaction, categories?: Category[]) { const category = categories?.find((item) => item.id === transaction.category_id); return category?.parent_name ?? category?.name ?? transaction.category; }
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
function viewTitle(view: View) { return ({ transactions: "Transactions", accounts: "Accounts", cards: "Credit cards", imports: "Imports", mailboxes: "Mailboxes", home: "Home" })[view]; }
function viewSubtitle(view: View) { return ({ transactions: "Search, review, and categorise your ledger.", accounts: "Your savings accounts and recorded balances.", cards: "Card activity is separate from your bank balance.", imports: "Review statement data before it reaches the ledger.", mailboxes: "Connect and manage your Gmail transaction sources.", home: "Your money, clearly organised." })[view]; }
function navIcon(view: View) { return ({ home: "⌂", transactions: "↔", accounts: "⌑", cards: "▣", imports: "⇧", mailboxes: "✉" })[view]; }
