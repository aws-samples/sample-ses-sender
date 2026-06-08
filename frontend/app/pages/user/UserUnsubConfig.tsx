"use client";
import React, { useState, useEffect } from "react";
import { API, authH, useAuth, useToast, Card, Btn, Input } from "../../components/shared";
import { useT } from "../../i18n";

const DEFAULT_REASONS = [
  { value: "too_frequent", label: "收到邮件太频繁" },
  { value: "not_relevant", label: "内容与我无关" },
  { value: "never_subscribed", label: "我从未订阅过" },
  { value: "prefer_other", label: "我更喜欢其他渠道获取信息" },
  { value: "other", label: "其他原因" },
];

export default function UserUnsubConfig() {
  const t = useT();
  const { token } = useAuth(); const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState({ title: "", subtitle: "", success: "", logo: "", color: "", reasons: DEFAULT_REASONS });
  const [useCustom, setUseCustom] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API}/user/unsub-config`, { headers: authH(token) });
        if (r.ok) {
          const d = await r.json();
          if (d && Object.keys(d).length > 0) {
            setF({ title: d.title || "", subtitle: d.subtitle || "", success: d.success || "", logo: d.logo || "", color: d.color || "", reasons: d.reasons || DEFAULT_REASONS });
            setUseCustom(true);
          }
        }
      } catch { }
      finally { setLoading(false); }
    })();
  }, []);

  const save = async () => {
    setSaving(true);
    try {
      const body = useCustom ? f : {};
      const r = await fetch(`${API}/user/unsub-config`, { method: "PUT", headers: authH(token), body: JSON.stringify(body) });
      if (r.ok) toast("success", useCustom ? t("unsub.configSaved") : t("unsub.restoredDefault"));
      else { const e = await r.json(); toast("error", t("unsub.saveFailed"), e.detail); }
    } catch { toast("error", t("common.networkError")); }
    finally { setSaving(false); }
  };

  const updateReason = (idx: number, field: "value" | "label", val: string) => {
    const nr = [...f.reasons]; nr[idx] = { ...nr[idx], [field]: val }; setF({ ...f, reasons: nr });
  };
  const addReason = () => setF({ ...f, reasons: [...f.reasons, { value: `reason_${f.reasons.length + 1}`, label: "" }] });
  const removeReason = (idx: number) => setF({ ...f, reasons: f.reasons.filter((_, i) => i !== idx) });

  if (loading) return <div className="flex items-center justify-center h-32 text-gray-400">{t("common.loading")}</div>;

  return <div className="max-w-3xl space-y-6">
    <Card title={t("unsub.customTitle")}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="rounded accent-indigo-500 w-4 h-4" checked={useCustom} onChange={e => setUseCustom(e.target.checked)} />
            <span className="text-sm font-medium text-gray-700">{t("unsub.useCustom")}</span>
          </label>
          <span className="text-xs text-gray-400">{useCustom ? t("unsub.overrideSystemDefault") : t("unsub.useAdminDefault")}</span>
        </div>

        {useCustom && <>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("unsub.pageTitle")}</label>
              <Input value={f.title} onChange={(e: any) => setF({ ...f, title: e.target.value })} placeholder={t("unsubPage.defaultTitle")} />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("unsub.successText")}</label>
              <Input value={f.success} onChange={(e: any) => setF({ ...f, success: e.target.value })} placeholder={t("unsubPage.defaultSuccess")} />
            </div>
          </div>

          <div>
            <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("unsub.pageSubtitle")}</label>
            <Input value={f.subtitle} onChange={(e: any) => setF({ ...f, subtitle: e.target.value })} placeholder={t("unsubPage.defaultSubtitle")} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("unsub.brandColor")}</label>
              <div className="flex gap-2 items-center">
                <input type="color" value={f.color || "#667eea"} onChange={(e: any) => setF({ ...f, color: e.target.value })} className="w-10 h-10 rounded-lg border border-gray-200 cursor-pointer" />
                <Input value={f.color} onChange={(e: any) => setF({ ...f, color: e.target.value })} placeholder="#667eea" className="flex-1" />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700 mb-1.5 block">{t("unsub.logoUrl")}</label>
              <Input value={f.logo} onChange={(e: any) => setF({ ...f, logo: e.target.value })} placeholder="https://example.com/logo.png" />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">{t("unsub.reasons")}</label>
              <button onClick={addReason} className="text-xs text-indigo-600 hover:text-indigo-800">{t("unsub.addOption")}</button>
            </div>
            <div className="space-y-2">
              {f.reasons.map((r, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <Input value={r.value} onChange={(e: any) => updateReason(i, "value", e.target.value)} placeholder="value" className="w-36 text-xs font-mono" />
                  <Input value={r.label} onChange={(e: any) => updateReason(i, "label", e.target.value)} placeholder={t("unsub.displayText")} className="flex-1" />
                  <button onClick={() => removeReason(i)} className="text-red-400 hover:text-red-600 text-sm px-2">×</button>
                </div>
              ))}
            </div>
          </div>
        </>}

        <div className="flex items-center gap-3 pt-2 border-t border-gray-100">
          <Btn onClick={save} disabled={saving}>{saving ? t("common.savingMsg") : t("unsub.saveConfig")}</Btn>
          {useCustom && f.color && <div className="w-6 h-6 rounded" style={{ background: f.color }} />}
        </div>
      </div>
    </Card>
  </div>;
}
