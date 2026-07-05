import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, LineChart, Line, CartesianGrid,
} from "recharts";
import {
  DollarSign, TrendingUp, Wallet, AlertTriangle, Calendar, CheckSquare, FolderKanban,
  Target, Percent, Layers, Plus, ArrowUpRight, ArrowRight,
} from "lucide-react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { STAGE_CONFIG } from "@/lib/statusConfig";
import { formatDistanceToNow, format } from "date-fns";
import { useAuth } from "@/contexts/AuthContext";

function KpiCard({ icon: Icon, label, value, sub, testId }) {
  return (
    <Card data-testid={testId} className="p-5 border-white/10 bg-surface-1 hover:border-white/20 transition-colors">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-graphite">{label}</span>
        <Icon className="h-4 w-4 text-graphite" />
      </div>
      <p className="font-display text-2xl font-bold tracking-tight">{value}</p>
      {sub && <p className="mt-1 text-xs text-ash">{sub}</p>}
    </Card>
  );
}

const currency = (n) => `$${(n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [finance, setFinance] = useState(null);
  const [activity, setActivity] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [s, f, a] = await Promise.all([
          api.get("/dashboard/stats"),
          api.get("/finance/summary"),
          api.get("/dashboard/activity?limit=8"),
        ]);
        setStats(s.data);
        setFinance(f.data);
        setActivity(a.data);
      } catch (e) {}
    })();
  }, []);

  if (!stats) {
    return (
      <div className="p-6 space-y-6" data-testid="dashboard-loading">
        <Skeleton className="h-8 w-64 bg-surface-1" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28 bg-surface-1" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6" data-testid="dashboard-page">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold tracking-tight">Welcome back, {user?.name?.split(" ")[0]}</h1>
          <p className="text-sm text-graphite mt-1">Here's what's happening across your agency today.</p>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="outline" className="gap-1.5 border-white/10 bg-surface-1" data-testid="quick-action-new-lead">
            <Link to="/crm?new=1"><Plus className="h-3.5 w-3.5" /> New Lead</Link>
          </Button>
          <Button asChild size="sm" className="gap-1.5" data-testid="quick-action-new-invoice">
            <Link to="/invoices?new=1"><Plus className="h-3.5 w-3.5" /> New Invoice</Link>
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiCard testId="kpi-revenue" icon={DollarSign} label="Revenue" value={currency(stats.revenue)} sub="Total paid to date" />
        <KpiCard testId="kpi-mrr" icon={TrendingUp} label="MRR" value={currency(stats.mrr)} sub="Monthly recurring" />
        <KpiCard testId="kpi-arr" icon={TrendingUp} label="ARR" value={currency(stats.arr)} sub="Annualized" />
        <KpiCard testId="kpi-profit" icon={Wallet} label="Profit" value={currency(stats.profit)} sub={`Expenses: ${currency(stats.expenses)}`} />
        <KpiCard testId="kpi-outstanding" icon={AlertTriangle} label="Outstanding" value={currency(stats.outstanding)} sub="Unpaid invoices" />
        <KpiCard testId="kpi-pipeline" icon={Layers} label="Pipeline Value" value={currency(stats.pipeline_value)} sub={`${stats.total_leads} leads`} />
        <KpiCard testId="kpi-conversion" icon={Percent} label="Lead Conversion" value={`${stats.conversion_rate}%`} sub="Won vs closed" />
        <KpiCard testId="kpi-avg-deal" icon={Target} label="Avg Deal Size" value={currency(stats.avg_deal_size)} sub="Per won deal" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5 border-white/10 bg-surface-1" data-testid="sales-funnel-chart">
          <p className="font-display text-sm font-semibold mb-4">Sales Funnel</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={stats.sales_funnel} layout="vertical" margin={{ left: 20 }}>
              <XAxis type="number" hide />
              <YAxis
                type="category"
                dataKey="stage"
                tickFormatter={(v) => STAGE_CONFIG[v]?.label || v}
                width={110}
                tick={{ fill: "#85858C", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip contentStyle={{ background: "#18181A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="count" fill="#3B82F6" radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </Card>

        <Card className="p-5 border-white/10 bg-surface-1" data-testid="revenue-trend-chart">
          <p className="font-display text-sm font-semibold mb-4">Revenue Trend</p>
          {finance?.revenue_by_month?.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={finance.revenue_by_month}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="month" tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ background: "#18181A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 }} />
                <Line type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[220px] items-center justify-center text-sm text-graphite">No revenue data yet</div>
          )}
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="p-5 border-white/10 bg-surface-1" data-testid="widget-todays-tasks">
          <div className="flex items-center justify-between mb-3">
            <p className="font-display text-sm font-semibold flex items-center gap-2"><CheckSquare className="h-4 w-4" /> Today's Tasks</p>
            <Link to="/tasks" className="text-xs text-graphite hover:text-foreground flex items-center gap-1">All <ArrowRight className="h-3 w-3" /></Link>
          </div>
          {stats.todays_tasks.length === 0 ? (
            <p className="text-sm text-graphite py-6 text-center">No tasks due today</p>
          ) : (
            <div className="space-y-2">
              {stats.todays_tasks.map((t) => (
                <div key={t.id} className="flex items-center gap-2 text-sm rounded-lg bg-surface-2 px-3 py-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                  <span className="truncate">{t.title}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5 border-white/10 bg-surface-1" data-testid="widget-upcoming-meetings">
          <div className="flex items-center justify-between mb-3">
            <p className="font-display text-sm font-semibold flex items-center gap-2"><Calendar className="h-4 w-4" /> Upcoming Meetings</p>
          </div>
          {stats.upcoming_meetings.length === 0 ? (
            <p className="text-sm text-graphite py-6 text-center">No upcoming meetings</p>
          ) : (
            <div className="space-y-2">
              {stats.upcoming_meetings.map((m) => (
                <div key={m.id} className="rounded-lg bg-surface-2 px-3 py-2">
                  <p className="text-sm truncate">{m.title}</p>
                  <p className="text-xs font-mono text-graphite">{format(new Date(m.start_time), "MMM d, h:mm a")}</p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-5 border-white/10 bg-surface-1" data-testid="widget-recent-activity">
          <div className="flex items-center justify-between mb-3">
            <p className="font-display text-sm font-semibold flex items-center gap-2"><ArrowUpRight className="h-4 w-4" /> Recent Activity</p>
          </div>
          {activity.length === 0 ? (
            <p className="text-sm text-graphite py-6 text-center">No recent activity</p>
          ) : (
            <div className="space-y-3 max-h-[220px] overflow-y-auto scrollbar-thin">
              {activity.map((a) => (
                <div key={a.id} className="text-sm">
                  <p className="text-ash line-clamp-2">{a.content}</p>
                  <p className="text-[10px] font-mono text-carbon mt-0.5">{formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}</p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <Card className="p-5 border-white/10 bg-surface-1 flex items-center justify-between" data-testid="widget-active-projects">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.15em] text-graphite mb-1">Active Projects</p>
            <p className="font-display text-2xl font-bold">{stats.active_projects_count}</p>
          </div>
          <FolderKanban className="h-8 w-8 text-graphite" />
        </Card>
        <Card className="p-5 border-white/10 bg-surface-1 flex items-center justify-between" data-testid="widget-at-risk-projects">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.15em] text-graphite mb-1">Projects At Risk</p>
            <p className="font-display text-2xl font-bold text-danger">{stats.at_risk_projects_count}</p>
          </div>
          <AlertTriangle className="h-8 w-8 text-danger/60" />
        </Card>
      </div>
    </div>
  );
}
