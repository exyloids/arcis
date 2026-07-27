"use client";

import { ChangeEvent, FormEvent, useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Account = { id: string; display_name: string; institution_code: string; account_type: string };
type Transaction = {
  id: string;
  transaction_date: string;
  narration: string;
  amount: string;
  currency: string;
  direction: string;
  account_name: string;
  category: string | null;
  category_id: string | null;
};
type Category = { id: string; name: string };
type TransactionPage = { items: Transaction[]; next_cursor: string | null };
type Preview = {
  import: { id: string; filename: string; row_count: number; valid_row_count: number; invalid_row_count: number; state: string };
  rows: Transaction[];
  errors: Array<{ ordinal: number; message: string }>;
};
type Report = { income: string; expense: string; categories: Array<{ category: string; amount: string }> };
type ImportItem = { id: string; filename: string; state: string; row_count: number; valid_row_count: number; invalid_row_count: number; duplicate_count: number; created_at: string; confirmed_at: string | null };
type Inspection = { headers: string[]; suggested_mapping: Record<string, string>; sample_row_count: number };
type Mapping = Record<string, string>;
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
  return response.json() as Promise<T>;
}

export default function HomePage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [mapping, setMapping] = useState<Mapping>({});
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const [ledgerAccountId, setLedgerAccountId] = useState("");
  const [ledgerCategoryId, setLedgerCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [evidence, setEvidence] = useState<Array<Record<string, string>> | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const month = new Date().toISOString().slice(0, 7);

  async function refresh() {
    const ledgerParams = new URLSearchParams({ month });
    if (ledgerAccountId) ledgerParams.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) ledgerParams.set("category_id", ledgerCategoryId);
    if (search.trim()) ledgerParams.set("q", search.trim());
    const [nextAccounts, nextCategories, transactionPage, nextReport, nextImports] = await Promise.all([
      request<Account[]>("/api/v1/financial-accounts"),
      request<Category[]>("/api/v1/categories"),
      request<TransactionPage>(`/api/v1/transactions/page?${ledgerParams}`),
      request<Report>(`/api/v1/reports/monthly?month=${month}`),
      request<ImportItem[]>("/api/v1/imports"),
    ]);
    setAccounts(nextAccounts);
    setCategories(nextCategories);
    setTransactions(transactionPage.items);
    setNextCursor(transactionPage.next_cursor);
    setReport(nextReport);
    setImports(nextImports);
    if (!accountId && nextAccounts[0]) setAccountId(nextAccounts[0].id);
  }

  useEffect(() => { void refresh().catch((error: Error) => setMessage(error.message)); }, []);

  async function createAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await request("/api/v1/financial-accounts", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.fromEntries(form)),
      });
      event.currentTarget.reset();
      setMessage("Account created.");
      await refresh();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function inspectFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accountId || !file) return setMessage("Select an account and CSV/XLSX statement.");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await request<Inspection>("/api/v1/imports/inspect", { method: "POST", body });
      setInspection(result); setMapping(result.suggested_mapping);
      setMessage(`Found ${result.sample_row_count} rows. Review the column mapping before creating a preview.`);
    } catch (error) { setMessage((error as Error).message); }
  }

  async function createPreview() {
    if (!accountId || !file) return;
    const missing = mappingFields.filter(([field, , required]) => required && !mapping[field]);
    if (missing.length) return setMessage(`Map required columns: ${missing.map(([, label]) => label).join(", ")}.`);
    const body = new FormData(); body.append("file", file);
    body.append("column_mapping", JSON.stringify(Object.fromEntries(Object.entries(mapping).filter(([, value]) => value))));
    try {
      const result = await request<Preview>(`/api/v1/imports?account_id=${accountId}`, { method: "POST", body });
      setPreview(result); setInspection(null); setMessage("Review the parsed rows before confirmation.");
    } catch (error) { setMessage((error as Error).message); }
  }

  async function confirmImport() {
    if (!preview) return;
    try {
      const result = await request<{ created: number; duplicates: number }>(`/api/v1/imports/${preview.import.id}/confirm`, { method: "POST" });
      setMessage(`Import confirmed: ${result.created} transactions created, ${result.duplicates} duplicates ignored.`);
      setPreview(null); setFile(null); await refresh();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function cancelImport(importId: string) {
    try {
      await request<void>(`/api/v1/imports/${importId}/cancel`, { method: "POST" });
      if (preview?.import.id === importId) setPreview(null);
      setMessage("Import cancelled and its staged document removed.");
      await refresh();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function openImport(importId: string) {
    try {
      const result = await request<Preview>(`/api/v1/imports/${importId}`);
      setPreview(result); setMessage("Viewing stored import preview.");
    } catch (error) { setMessage((error as Error).message); }
  }

  async function updateCategory(transactionId: string, categoryId: string) {
    try {
      await request(`/api/v1/transactions/${transactionId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ category_id: categoryId || null }) });
      setMessage("Transaction category updated."); await refresh();
    } catch (error) { setMessage((error as Error).message); }
  }

  async function showEvidence(transactionId: string) {
    try { setEvidence(await request<Array<Record<string, string>>>(`/api/v1/transactions/${transactionId}/evidence`)); }
    catch (error) { setMessage((error as Error).message); }
  }

  async function loadMore() {
    if (!nextCursor) return;
    const params = new URLSearchParams({ month, cursor: nextCursor });
    if (ledgerAccountId) params.set("account_id", ledgerAccountId);
    if (ledgerCategoryId) params.set("category_id", ledgerCategoryId);
    if (search.trim()) params.set("q", search.trim());
    try {
      const page = await request<TransactionPage>(`/api/v1/transactions/page?${params}`);
      setTransactions([...transactions, ...page.items]); setNextCursor(page.next_cursor);
    } catch (error) { setMessage((error as Error).message); }
  }

  return <main className="workspace">
    <header><p className="eyebrow">ARCIS · MANUAL LEDGER</p><h1>Statements into a trustworthy ledger.</h1><p>Upload a structured statement, review every parsed row, then confirm it once.</p></header>
    {message && <p className="notice" role="status">{message}</p>}
    <section className="grid">
      <form className="card" onSubmit={createAccount}><h2>Add account</h2>
        <input name="display_name" placeholder="Display name" required />
        <input name="institution_code" placeholder="Institution, e.g. icici" required />
        <input name="product_name" placeholder="Product name" required />
        <input name="masked_identifier" placeholder="Masked identifier, e.g. XX1234" />
        <select name="account_type" defaultValue="bank_account"><option value="bank_account">Bank account</option><option value="credit_card">Credit card</option></select>
        <input name="currency" defaultValue="INR" required /><button type="submit">Create account</button>
      </form>
      <form className="card" onSubmit={inspectFile}><h2>Import statement</h2>
        <select value={accountId} onChange={(event) => setAccountId(event.target.value)} required><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select>
        <input type="file" accept=".csv,.xlsx" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required />
        <p className="hint">CSV/XLSX only · maximum 10 MiB</p><button type="submit">Inspect columns</button>
      </form>
      <section className="card"><h2>This month</h2><p className="metric">Income ₹{report?.income ?? "0"}</p><p className="metric expense">Expense ₹{report?.expense ?? "0"}</p></section>
    </section>
    {inspection && <section className="card wide"><h2>Column mapping · {file?.name}</h2><p>Review the detected columns before parsing the statement.</p><div className="mapping-grid">{mappingFields.map(([field, label, required]) => <label key={field}>{label}{required ? " *" : ""}<select value={mapping[field] ?? ""} onChange={(event) => setMapping({ ...mapping, [field]: event.target.value })}><option value="">{required ? "Select column" : "Not available"}</option>{inspection.headers.map((header) => <option key={header} value={header}>{header}</option>)}</select></label>)}</div><button onClick={() => void createPreview()}>Create preview</button></section>}
    {preview && <section className="card wide"><h2>Import preview · {preview.import.filename}</h2><p>{preview.import.valid_row_count} valid and {preview.import.invalid_row_count} invalid rows from {preview.import.row_count} source rows.</p>{preview.errors.length > 0 && <div className="import-errors"><h3>Rows needing review</h3><ul>{preview.errors.map((error) => <li key={error.ordinal}>Row {error.ordinal}: {error.message}</li>)}</ul></div>}<LedgerTable transactions={preview.rows} />{preview.import.state === "preview_ready" && <button onClick={confirmImport}>Confirm valid rows</button>}</section>}
    <section className="card wide"><h2>Import history</h2>{imports.length ? <div className="table-wrap"><table><thead><tr><th>File</th><th>Status</th><th>Valid / invalid</th><th>Duplicates</th><th>Created</th><th>Action</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td>{item.filename}</td><td><span className={`state ${item.state}`}>{item.state.replaceAll("_", " ")}</span></td><td>{item.valid_row_count} / {item.invalid_row_count}</td><td>{item.duplicate_count}</td><td>{new Date(item.created_at).toLocaleString()}</td><td><button className="secondary" onClick={() => void openImport(item.id)}>View</button>{item.state === "preview_ready" && <button className="secondary" onClick={() => void cancelImport(item.id)}>Cancel</button>}</td></tr>)}</tbody></table></div> : <p className="hint">No imports yet.</p>}</section>
    <section className="card wide"><h2>Transactions · {month}</h2><div className="ledger-filters"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search narration" /><select value={ledgerAccountId} onChange={(event) => setLedgerAccountId(event.target.value)}><option value="">All accounts</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select><select value={ledgerCategoryId} onChange={(event) => setLedgerCategoryId(event.target.value)}><option value="">All categories</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select><button onClick={() => void refresh()}>Apply filters</button></div><LedgerTable transactions={transactions} categories={categories} onCategoryChange={updateCategory} onEvidence={showEvidence} />{nextCursor && <button className="secondary load-more" onClick={() => void loadMore()}>Load more</button>}</section>
    {evidence && <section className="card wide"><h2>Transaction evidence</h2>{evidence.length ? <pre>{JSON.stringify(evidence, null, 2)}</pre> : <p className="hint">No source evidence found.</p>}<button className="secondary" onClick={() => setEvidence(null)}>Close</button></section>}
  </main>;
}

function LedgerTable({ transactions, categories, onCategoryChange, onEvidence }: { transactions: Transaction[]; categories?: Category[]; onCategoryChange?: (id: string, categoryId: string) => Promise<void>; onEvidence?: (id: string) => Promise<void> }) {
  if (!transactions.length) return <p className="hint">No transactions yet.</p>;
  return <div className="table-wrap"><table><thead><tr><th>Date</th><th>Account</th><th>Narration</th><th>Category</th><th>Amount</th><th>Evidence</th></tr></thead><tbody>{transactions.map((transaction, index) => <tr key={transaction.id ?? index}><td>{transaction.transaction_date}</td><td>{transaction.account_name ?? "Selected account"}</td><td>{transaction.narration}</td><td>{categories ? <select value={transaction.category_id ?? ""} onChange={(event) => void onCategoryChange?.(transaction.id, event.target.value)}><option value="">Uncategorized</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select> : transaction.category ?? "Uncategorized"}</td><td className={transaction.direction === "debit" ? "debit" : "credit"}>{transaction.direction === "debit" ? "−" : "+"} ₹{transaction.amount}</td><td>{onEvidence && <button className="secondary" onClick={() => void onEvidence(transaction.id)}>View</button>}</td></tr>)}</tbody></table></div>;
}
