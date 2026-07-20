import { useEffect, useState } from "react";
import { ShieldAlert, Send } from "lucide-react";
import api from "@/lib/api";
import PageHeader from "@/components/PageHeader";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import IdentitiesPanel from "@/components/sdr/IdentitiesPanel";
import SuppressionPanel from "@/components/sdr/SuppressionPanel";
import PreflightTester from "@/components/sdr/PreflightTester";
import QuotaPanel from "@/components/sdr/QuotaPanel";

export default function SDRDeliverability() {
  const [settings, setSettings] = useState(null);

  useEffect(() => {
    api.get("/sdr/settings").then(({ data }) => setSettings(data)).catch(() => {});
  }, []);

  const emailOff = settings && !settings.channels?.email;

  return (
    <div className="p-6 space-y-5" data-testid="sdr-deliverability-page">
      <PageHeader
        title="Deliverability"
        description="Sending identities, DNS, warm-up and the suppression list"
      />

      {settings?.kill_switch && (
        <Card className="p-4 bg-danger/10 border-danger/20" data-testid="sdr-deliverability-kill">
          <p className="text-sm text-danger flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" /> Kill switch is on — nothing will send
            regardless of what is configured here.
          </p>
        </Card>
      )}

      {emailOff && !settings?.kill_switch && (
        <Card className="p-4 bg-surface-1 border-white/10" data-testid="sdr-deliverability-email-off">
          <p className="text-sm text-ash flex items-center gap-2">
            <Send className="h-4 w-4 text-carbon" /> Email sending is switched off
          </p>
          <p className="text-xs text-graphite mt-1">
            That is the intended state until a domain passes DNS and finishes warm-up.
            Set an identity up here first, then enable the email channel on the AI SDR page.
          </p>
        </Card>
      )}

      <Tabs defaultValue="identities">
        <TabsList className="bg-surface-2">
          <TabsTrigger value="identities" data-testid="sdr-tab-identities">Sending identities</TabsTrigger>
          <TabsTrigger value="quota" data-testid="sdr-tab-quota">Volume &amp; quota</TabsTrigger>
          <TabsTrigger value="suppression" data-testid="sdr-tab-suppression">Suppression list</TabsTrigger>
          <TabsTrigger value="preflight" data-testid="sdr-tab-preflight">Test a send</TabsTrigger>
        </TabsList>

        <TabsContent value="identities" className="mt-4">
          <IdentitiesPanel />
        </TabsContent>
        <TabsContent value="quota" className="mt-4">
          <QuotaPanel />
        </TabsContent>
        <TabsContent value="suppression" className="mt-4">
          <SuppressionPanel />
        </TabsContent>
        <TabsContent value="preflight" className="mt-4">
          <PreflightTester />
        </TabsContent>
      </Tabs>
    </div>
  );
}
