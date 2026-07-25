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
};
type Preview = { import: { id: string; filename: string; row_count: number }; rows: Transaction[] };
type Report = { income: string; expense: string; categories: Array<{ category: string; amount: string }> };

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
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const month = new Date().toISOString().slice(0, 7);

  async function refresh() {
    const [nextAccounts, nextTransactions, nextReport] = await Promise.all([
      request<Account[]>("/api/v1/financial-accounts"),
      request<Transaction[]>(`/api/v1/transactions?month=${month}`),
      request<Report>(`/api/v1/reports/monthly?month=${month}`),
    ]);
    setAccounts(nextAccounts);
    setTransactions(nextTransactions);
    setReport(nextReport);
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

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accountId || !file) return setMessage("Select an account and CSV/XLSX statement.");
    const body = new FormData(); body.append("file", file);
    try {
      const result = await request<Preview>(`/api/v1/imports?account_id=${accountId}`, { method: "POST", body });
      setPreview(result); setMessage("Review the parsed rows before confirmation.");
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
      <form className="card" onSubmit={upload}><h2>Import statement</h2>
        <select value={accountId} onChange={(event) => setAccountId(event.target.value)} required><option value="">Select account</option>{accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}</select>
        <input type="file" accept=".csv,.xlsx" onChange={(event: ChangeEvent<HTMLInputElement>) => setFile(event.target.files?.[0] ?? null)} required />
        <p className="hint">CSV/XLSX only · maximum 10 MiB</p><button type="submit">Preview import</button>
      </form>
      <section className="card"><h2>This month</h2><p className="metric">Income ₹{report?.income ?? "0"}</p><p className="metric expense">Expense ₹{report?.expense ?? "0"}</p></section>
    </section>
    {preview && <section className="card wide"><h2>Import preview · {preview.import.filename}</h2><p>{preview.import.row_count} rows will be recorded as source evidence.</p><LedgerTable transactions={preview.rows} /><button onClick={confirmImport}>Confirm import</button></section>}
    <section className="card wide"><h2>Transactions · {month}</h2><LedgerTable transactions={transactions} /></section>
  </main>;
}

function LedgerTable({ transactions }: { transactions: Transaction[] }) {
  if (!transactions.length) return <p className="hint">No transactions yet.</p>;
  return <div className="table-wrap"><table><thead><tr><th>Date</th><th>Account</th><th>Narration</th><th>Category</th><th>Amount</th></tr></thead><tbody>{transactions.map((transaction, index) => <tr key={transaction.id ?? index}><td>{transaction.transaction_date}</td><td>{transaction.account_name ?? "Selected account"}</td><td>{transaction.narration}</td><td>{transaction.category ?? "Uncategorized"}</td><td className={transaction.direction === "debit" ? "debit" : "credit"}>{transaction.direction === "debit" ? "−" : "+"} ₹{transaction.amount}</td></tr>)}</tbody></table></div>;
}
