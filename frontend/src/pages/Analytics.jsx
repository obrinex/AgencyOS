import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell } from "recharts";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PROJECT_STATUS_CONFIG } from "@/lib/statusConfig";
import { formatMoney } from "@/lib/currency";

const PIE_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#85858C", "#B5B5BC"];
const tooltipStyle = { background: "#18181A", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, fontSize: 12 };

export default function Analytics() {
  const [data, setData] = useState(null);

  useEffect(() => {
    (async () => {
      const [leads, clients, projects, finance] = await Promise.all([
        api.get("/leads"), api.get("/clients"), api.get("/projects"), api.get("/finance/summary"),
      ]);
      setData({ leads: leads.data, clients: clients.data, projects: projects.data, finance: finance.data });
    })();
  }, []);

  if (!data) return <div className="p-6"><Skeleton className="h-64 bg-surface-1" /></div>;

  const sourceCount = {};
  data.leads.forEach((l) => { sourceCount[l.source || "manual"] = (sourceCount[l.source || "manual"] || 0) + 1; });
  const sourceData = Object.entries(sourceCount).map(([name, value]) => ({ name, value }));

  const statusCount = {};
  data.projects.forEach((p) => { statusCount[p.status] = (statusCount[p.status] || 0) + 1; });
  const statusData = Object.entries(statusCount).map(([status, count]) => ({ status: PROJECT_STATUS_CONFIG[status]?.label || status, count }));

  const ltvData = data.clients.slice(0, 8).map((c) => ({ name: c.company_name, ltv: c.revenue_generated || 0 }));

  const wonCount = data.leads.filter((l) => l.stage === "won").length;
  const lostCount = data.leads.filter((l) => l.stage === "lost" || l.stage === "rejected").length;

  return (
    <div className="p-6 space-y-6" data-testid="analytics-page">
      <PageHeader title="Analytics" description="Sales, revenue, client & project intelligence" />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Deals Won</p><p className="font-display text-xl font-bold text-success">{wonCount}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Deals Lost</p><p className="font-display text-xl font-bold text-danger">{lostCount}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Total Clients</p><p className="font-display text-xl font-bold">{data.clients.length}</p></Card>
        <Card className="p-4 bg-surface-1 border-white/10"><p className="text-[10px] font-mono uppercase text-graphite">Avg Project Value</p><p className="font-display text-xl font-bold">{formatMoney(data.finance.avg_deal_size)}</p></Card>
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5 bg-surface-1 border-white/10">
          <p className="font-display text-sm font-semibold mb-4">Lead Sources</p>
          {sourceData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={sourceData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                  {sourceData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          ) : <div className="flex h-[240px] items-center justify-center text-sm text-graphite">No lead data yet</div>}
        </Card>

        <Card className="p-5 bg-surface-1 border-white/10">
          <p className="font-display text-sm font-semibold mb-4">Projects by Status</p>
          {statusData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={statusData}>
                <XAxis dataKey="status" tick={{ fill: "#85858C", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={tooltipStyle} />
                <Bar dataKey="count" fill="#3B82F6" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="flex h-[240px] items-center justify-center text-sm text-graphite">No project data yet</div>}
        </Card>
      </div>

      <Card className="p-5 bg-surface-1 border-white/10">
        <p className="font-display text-sm font-semibold mb-4">Client Lifetime Value</p>
        {ltvData.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={ltvData}>
              <XAxis dataKey="name" tick={{ fill: "#85858C", fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#85858C", fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="ltv" fill="#10B981" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <div className="flex h-[240px] items-center justify-center text-sm text-graphite">No client data yet</div>}
      </Card>
    </div>
  );
}
