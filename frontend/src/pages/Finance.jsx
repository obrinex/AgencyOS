import { useEffect, useState } from "react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell } from "recharts";
import { Plus, Trash2, Wallet, PiggyBank } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import DatePicker from "@/components/DatePicker";
import { formatMoney, EXPENSE_TYPES } from "@/lib/currency";
import { format } from "date-fns";
import { toast } from "sonner";

const EXPENSE_TYPE_LABELS = Object.fromEntries(EXPENSE_TYPES.map((t) => [t.value, t.label]));
const PIE_COLORS = { personal_withdrawal: "#F59E0B", business_expense: "#EF4444", unclassified: "#85858C" };
const tooltipStyle = { background: "#18181A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 };

const emptyForm = {
  category: "Software", description: "", amount: "", date: new Date().toISOString().slice(0, 10),
  vendor: "", currency: "INR", conversion_rate: 1, expense_type: "unclassified",
};

export default function Finance() {
  const [summary, setSummary] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);

  const load = async () => {
    const [s, e] = await Promise.all([api.get("/finance/summary"), api.get("/expenses")]);
    setSummary(s.data);
    setExpenses(e.data);
  };

  useEffect(() => { load(); }, []);

  const createExpense = async (e) => {
    e.preventDefault();
    try {
      await api.post("/expenses", { ...form, amount: parseFloat(form.amount), conversion_rate: parseFloat(form.conversion_rate) || 1 });
      toast.success("Expense added");
      setOpen(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
  };

  const deleteExpense = async (id) => {
    await api.delete(`/expenses/${id}`);
    load();
  };

  if (!summary) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const breakdownData = Object.entries(summary.expense_breakdown || {})
    .filter(([, v]) => v > 0)
    .map(([type, value]) => ({ name: EXPENSE_TYPE_LABELS[type] || type, type, value }));

  return (
    <div className="p-6 space-y-6" data-testid="finance-page">
      <PageHeader title="Finance" description="Revenue, expenses & profitability overview (base currency: INR)" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Revenue</p><p data-testid="finance-kpi-revenue" className="font-display text-xl font-bold text-success">{formatMoney(summary.revenue)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Expenses</p><p data-testid="finance-kpi-expenses" className="font-display text-xl font-bold text-danger">{formatMoney(summary.expenses)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Profit</p><p data-testid="finance-kpi-profit" className="font-display text-xl font-bold">{formatMoney(summary.profit)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Gross Margin</p><p className="font-display text-xl font-bold">{summary.gross_margin}%</p></Card>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">MRR</p><p className="font-display text-xl font-bold">{formatMoney(summary.mrr)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">ARR</p><p className="font-display text-xl font-bold">{formatMoney(summary.arr)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Outstanding</p><p className="font-display text-xl font-bold text-warning">{formatMoney(summary.outstanding)}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Pipeline Value</p><p className="font-display text-xl font-bold">{formatMoney(summary.pipeline_value)}</p></Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5 bg-surface-1 border-white/10">
          <p className="font-display text-sm font-semibold mb-4">Revenue Over Time</p>
          {summary.revenue_by_month?.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={summary.revenue_by_month}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatMoney(v)} />
                <Line type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="flex h-[240px] items-center justify-center text-sm text-graphite">No revenue data yet</div>}
        </Card>

        <Card className="p-5 bg-surface-1 border-white/10" data-testid="expense-breakdown-card">
          <p className="font-display text-sm font-semibold mb-4 flex items-center gap-2"><PiggyBank className="h-4 w-4" /> Expense Breakdown</p>
          {breakdownData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={breakdownData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label={(d) => d.name}>
                  {breakdownData.map((d, i) => <Cell key={i} fill={PIE_COLORS[d.type] || "#85858C"} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatMoney(v)} />
              </PieChart>
            </ResponsiveContainer>
          ) : <div className="flex h-[240px] items-center justify-center text-sm text-graphite">No expenses recorded yet</div>}
        </Card>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <p className="font-display font-semibold flex items-center gap-2"><Wallet className="h-4 w-4" /> Expenses</p>
          <Button data-testid="open-create-expense-btn" size="sm" className="gap-1.5" onClick={() => setOpen(true)}><Plus className="h-3.5 w-3.5" /> Add Expense</Button>
        </div>
        <div className="space-y-2" data-testid="expenses-list">
          {expenses.length === 0 && <p className="text-sm text-graphite py-6 text-center">No expenses recorded</p>}
          {expenses.map((e) => (
            <div key={e.id} data-testid={`expense-row-${e.id}`} className="flex items-center justify-between rounded-lg border border-white/10 bg-surface-1 px-4 py-2.5">
              <div>
                <p className="text-sm">{e.description}</p>
                <p className="text-[10px] font-mono text-carbon">
                  {e.category} · {format(new Date(e.date), "MMM d, yyyy")} · <span className="uppercase">{EXPENSE_TYPE_LABELS[e.expense_type] || e.expense_type}</span>
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-2 text-graphite uppercase">{e.currency}</span>
                <span className="font-mono text-sm text-danger">-{formatMoney(e.amount, e.currency)}</span>
                <button data-testid={`delete-expense-${e.id}`} onClick={() => deleteExpense(e.id)} className="text-graphite hover:text-danger"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-surface-1 border-white/10" data-testid="create-expense-dialog">
          <DialogHeader><DialogTitle>Add Expense</DialogTitle></DialogHeader>
          <form onSubmit={createExpense} className="space-y-3">
            <div className="space-y-1"><Label>Description *</Label><Input data-testid="expense-form-description" required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1"><Label>Category</Label><Input data-testid="expense-form-category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1"><Label>Amount *</Label><Input data-testid="expense-form-amount" type="number" required value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="bg-surface-2 border-white/10" /></div>
              <div className="space-y-1">
                <Label>Currency</Label>
                <Select value={form.currency} onValueChange={(v) => setForm({ ...form, currency: v, conversion_rate: v === "INR" ? 1 : form.conversion_rate })}>
                  <SelectTrigger data-testid="expense-form-currency" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="INR">INR (₹)</SelectItem><SelectItem value="USD">USD ($)</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Conversion Rate (to ₹)</Label>
                <Input data-testid="expense-form-conversion-rate" type="number" step="0.01" disabled={form.currency === "INR"} value={form.conversion_rate} onChange={(e) => setForm({ ...form, conversion_rate: e.target.value })} className="bg-surface-2 border-white/10" />
              </div>
              <div className="space-y-1">
                <Label>Expense Type</Label>
                <Select value={form.expense_type} onValueChange={(v) => setForm({ ...form, expense_type: v })}>
                  <SelectTrigger data-testid="expense-form-type" className="bg-surface-2 border-white/10"><SelectValue /></SelectTrigger>
                  <SelectContent>{EXPENSE_TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-1"><Label>Date</Label><DatePicker testId="expense-form-date" value={form.date} onChange={(v) => setForm({ ...form, date: v })} /></div>
              <div className="space-y-1"><Label>Vendor</Label><Input data-testid="expense-form-vendor" value={form.vendor} onChange={(e) => setForm({ ...form, vendor: e.target.value })} className="bg-surface-2 border-white/10" /></div>
            </div>
            {form.currency !== "INR" && (
              <p className="text-xs text-graphite font-mono">
                ≈ {formatMoney((parseFloat(form.amount) || 0) * (parseFloat(form.conversion_rate) || 1))} in base currency
              </p>
            )}
            <DialogFooter><Button type="submit" data-testid="expense-form-submit">Add Expense</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
