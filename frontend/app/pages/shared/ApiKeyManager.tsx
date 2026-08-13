"use client";

import React, { useCallback, useEffect, useState } from "react";
import { API, Badge, Btn, Card, Input, Modal, authFetch, useAuth, useConfirm, useToast } from "../../components/shared";
import { useT } from "../../i18n";

type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
  scopes: string[];
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

type ScopeOption = { value: string; labelKey: string; adminOnly?: boolean };

const SCOPE_OPTIONS: ScopeOption[] = [
  { value: "profile:read", labelKey: "apiKeys.scope.profileRead" },
  { value: "profile:write", labelKey: "apiKeys.scope.profileWrite" },
  { value: "audience:read", labelKey: "apiKeys.scope.audienceRead" },
  { value: "audience:write", labelKey: "apiKeys.scope.audienceWrite" },
  { value: "templates:read", labelKey: "apiKeys.scope.templatesRead" },
  { value: "templates:write", labelKey: "apiKeys.scope.templatesWrite" },
  { value: "ai:use", labelKey: "apiKeys.scope.ai" },
  { value: "sending:read", labelKey: "apiKeys.scope.sendingRead" },
  { value: "sending:write", labelKey: "apiKeys.scope.sendingWrite" },
  { value: "scheduled:read", labelKey: "apiKeys.scope.scheduledRead" },
  { value: "scheduled:write", labelKey: "apiKeys.scope.scheduledWrite" },
  { value: "unsubscribe:read", labelKey: "apiKeys.scope.unsubscribeRead" },
  { value: "unsubscribe:write", labelKey: "apiKeys.scope.unsubscribeWrite" },
  { value: "admin:read", labelKey: "apiKeys.scope.adminRead", adminOnly: true },
  { value: "admin:write", labelKey: "apiKeys.scope.adminWrite", adminOnly: true },
];

const DEFAULT_SCOPES = ["profile:read", "audience:read", "templates:read", "sending:read"];

function formatDate(value: string | null, never: string) {
  if (!value) return never;
  return new Date(value).toLocaleString();
}

export default function ApiKeyManager() {
  const { token, user } = useAuth();
  const t = useT();
  const { toast } = useToast();
  const { confirm } = useConfirm();
  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [scopes, setScopes] = useState<string[]>(DEFAULT_SCOPES);
  const [creating, setCreating] = useState(false);
  const [newSecret, setNewSecret] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await authFetch(`${API}/user/api-keys`, token);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || t("common.failed"));
      setItems(Array.isArray(data) ? data : []);
    } catch (error) {
      toast("error", t("common.failed"), error instanceof Error ? error.message : String(error));
    } finally {
      setLoading(false);
    }
  }, [t, toast, token]);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleScope = (scope: string) => {
    setScopes(current => current.includes(scope) ? current.filter(item => item !== scope) : [...current, scope]);
  };

  const openCreate = () => {
    setName("");
    setExpiresAt("");
    setScopes(DEFAULT_SCOPES);
    setCreateOpen(true);
  };

  const createKey = async () => {
    if (!name.trim() || scopes.length === 0) return;
    setCreating(true);
    try {
      const response = await authFetch(`${API}/user/api-keys`, token, {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          scopes,
          expires_at: expiresAt ? new Date(expiresAt).toISOString() : null,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || t("common.failed"));
      setCreateOpen(false);
      setNewSecret(data.api_key);
      toast("success", t("apiKeys.created"));
      await load();
    } catch (error) {
      toast("error", t("common.failed"), error instanceof Error ? error.message : String(error));
    } finally {
      setCreating(false);
    }
  };

  const copySecret = async () => {
    await navigator.clipboard.writeText(newSecret);
    toast("success", t("apiKeys.copied"));
  };

  const revoke = async (item: ApiKeyItem) => {
    const accepted = await confirm(t("apiKeys.revokeTitle"), t("apiKeys.revokeConfirm").replace("{name}", item.name), t("apiKeys.revoke"));
    if (!accepted) return;
    try {
      const response = await authFetch(`${API}/user/api-keys/${item.id}`, token, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || t("common.failed"));
      toast("success", t("apiKeys.revoked"));
      await load();
    } catch (error) {
      toast("error", t("common.failed"), error instanceof Error ? error.message : String(error));
    }
  };

  const activeCount = items.filter(item => !item.revoked_at && (!item.expires_at || new Date(item.expires_at) > new Date())).length;

  return <>
    <Card
      title={t("apiKeys.title")}
      extra={<Btn onClick={openCreate}>{t("apiKeys.create")}</Btn>}
    >
      <div className="mb-5 rounded-xl border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm text-indigo-700">
        <p className="font-medium">{t("apiKeys.description")}</p>
        <p className="mt-1 text-xs text-indigo-500">{t("apiKeys.securityHint")}</p>
      </div>

      {loading ? <p className="py-10 text-center text-sm text-gray-400">{t("common.loading")}</p> :
        items.length === 0 ? <div className="py-12 text-center">
          <div className="mb-3 text-4xl">🔑</div>
          <p className="font-medium text-gray-700">{t("apiKeys.empty")}</p>
          <p className="mt-1 text-sm text-gray-400">{t("apiKeys.emptyHint")}</p>
        </div> :
        <div className="overflow-x-auto">
          <div className="mb-3 text-xs text-gray-400">{t("apiKeys.activeCount").replace("{count}", String(activeCount))}</div>
          <table className="w-full min-w-[760px] text-left">
            <thead><tr className="border-b border-gray-100 text-xs uppercase tracking-wide text-gray-400">
              <th className="px-3 py-3 font-medium">{t("apiKeys.name")}</th>
              <th className="px-3 py-3 font-medium">{t("apiKeys.key")}</th>
              <th className="px-3 py-3 font-medium">{t("apiKeys.scopes")}</th>
              <th className="px-3 py-3 font-medium">{t("apiKeys.lastUsed")}</th>
              <th className="px-3 py-3 font-medium">{t("apiKeys.expires")}</th>
              <th className="px-3 py-3 font-medium">{t("apiKeys.status")}</th>
              <th className="px-3 py-3"></th>
            </tr></thead>
            <tbody>{items.map(item => {
              const expired = Boolean(item.expires_at && new Date(item.expires_at) <= new Date());
              const inactive = Boolean(item.revoked_at) || expired;
              return <tr key={item.id} className="border-b border-gray-50 text-sm">
                <td className="px-3 py-4 font-medium text-gray-800">{item.name}</td>
                <td className="px-3 py-4 font-mono text-xs text-gray-500">{item.key_prefix}••••••••</td>
                <td className="max-w-[280px] px-3 py-4"><div className="flex flex-wrap gap-1">
                  {item.scopes.map(scope => <span key={scope} className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-500">{scope}</span>)}
                </div></td>
                <td className="px-3 py-4 text-xs text-gray-500">{formatDate(item.last_used_at, t("apiKeys.never"))}</td>
                <td className="px-3 py-4 text-xs text-gray-500">{formatDate(item.expires_at, t("apiKeys.neverExpires"))}</td>
                <td className="px-3 py-4"><Badge color={inactive ? "gray" : "green"}>{item.revoked_at ? t("apiKeys.statusRevoked") : expired ? t("apiKeys.statusExpired") : t("apiKeys.statusActive")}</Badge></td>
                <td className="px-3 py-4 text-right">{!item.revoked_at && <Btn variant="danger" size="sm" onClick={() => void revoke(item)}>{t("apiKeys.revoke")}</Btn>}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>}
    </Card>

    <Modal open={createOpen} onClose={() => setCreateOpen(false)} title={t("apiKeys.createTitle")} width={680}>
      <div className="space-y-5">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-gray-700">{t("apiKeys.name")}</span>
          <Input value={name} maxLength={100} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setName(event.target.value)} placeholder={t("apiKeys.namePlaceholder")} autoFocus />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-gray-700">{t("apiKeys.expiresOptional")}</span>
          <Input type="datetime-local" value={expiresAt} onChange={(event: React.ChangeEvent<HTMLInputElement>) => setExpiresAt(event.target.value)} />
        </label>
        <div>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">{t("apiKeys.selectScopes")}</span>
            <span className="text-xs text-gray-400">{t("apiKeys.selectedCount").replace("{count}", String(scopes.length))}</span>
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {SCOPE_OPTIONS.filter(option => !option.adminOnly || user.is_admin).map(option =>
              <label key={option.value} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${scopes.includes(option.value) ? "border-indigo-300 bg-indigo-50" : "border-gray-200 hover:border-gray-300"}`}>
                <input type="checkbox" className="mt-0.5 accent-indigo-600" checked={scopes.includes(option.value)} onChange={() => toggleScope(option.value)} />
                <span><span className="block font-mono text-xs font-medium text-gray-700">{option.value}</span><span className="mt-0.5 block text-xs text-gray-400">{t(option.labelKey)}</span></span>
              </label>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-gray-100 pt-4">
          <Btn variant="outline" onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Btn>
          <Btn disabled={creating || !name.trim() || scopes.length === 0} onClick={() => void createKey()}>{creating ? t("common.loading") : t("apiKeys.create")}</Btn>
        </div>
      </div>
    </Modal>

    <Modal open={Boolean(newSecret)} onClose={() => setNewSecret("")} title={t("apiKeys.secretTitle")} width={620}>
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">{t("apiKeys.secretWarning")}</div>
      <div className="mt-4 flex gap-2">
        <code className="min-w-0 flex-1 overflow-x-auto rounded-lg bg-gray-900 px-4 py-3 text-sm text-emerald-300">{newSecret}</code>
        <Btn onClick={() => void copySecret()}>{t("apiKeys.copy")}</Btn>
      </div>
      <div className="mt-5 flex justify-end"><Btn variant="outline" onClick={() => setNewSecret("")}>{t("apiKeys.saved")}</Btn></div>
    </Modal>
  </>;
}
