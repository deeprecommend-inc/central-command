'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface LLMProvider {
  provider: string;
  display_name: string;
  default_models: string[];
  description: string;
}

interface LLMSetting {
  id: number;
  provider: string;
  display_name: string;
  default_model: string | null;
  api_base_url: string | null;
  is_enabled: boolean;
  is_default: boolean;
  has_api_key: boolean;
  last_verified_at: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [settings, setSettings] = useState<LLMSetting[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [verifying, setVerifying] = useState<string | null>(null);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [modelInput, setModelInput] = useState('');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [providersRes, settingsRes] = await Promise.all([
        fetch('http://localhost:8006/llm-settings/providers'),
        fetch('http://localhost:8006/llm-settings'),
      ]);

      if (providersRes.ok) {
        const data = await providersRes.json();
        setProviders(data);
      }

      if (settingsRes.ok) {
        const data = await settingsRes.json();
        setSettings(data);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setMessage({ type: 'error', text: 'データの取得に失敗しました' });
    } finally {
      setLoading(false);
    }
  };

  const saveSetting = async (provider: string) => {
    setSaving(provider);
    setMessage(null);

    try {
      const response = await fetch(`http://localhost:8006/llm-settings/${provider}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: apiKeyInput || undefined,
          default_model: modelInput || undefined,
          is_enabled: true,
        }),
      });

      if (response.ok) {
        setMessage({ type: 'success', text: '設定を保存しました' });
        setEditingProvider(null);
        setApiKeyInput('');
        setModelInput('');
        await fetchData();
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || '保存に失敗しました' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: '保存に失敗しました' });
    } finally {
      setSaving(null);
    }
  };

  const verifySetting = async (provider: string) => {
    setVerifying(provider);
    setMessage(null);

    try {
      const response = await fetch(`http://localhost:8006/llm-settings/${provider}/verify`, {
        method: 'POST',
      });

      const result = await response.json();

      if (result.success) {
        setMessage({ type: 'success', text: result.message });
        await fetchData();
      } else {
        setMessage({ type: 'error', text: result.message });
      }
    } catch (error) {
      setMessage({ type: 'error', text: '検証に失敗しました' });
    } finally {
      setVerifying(null);
    }
  };

  const setAsDefault = async (provider: string) => {
    setSaving(provider);
    setMessage(null);

    try {
      const response = await fetch(`http://localhost:8006/llm-settings/${provider}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          is_default: true,
        }),
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'デフォルトプロバイダーを変更しました' });
        await fetchData();
      } else {
        setMessage({ type: 'error', text: '変更に失敗しました' });
      }
    } catch (error) {
      setMessage({ type: 'error', text: '変更に失敗しました' });
    } finally {
      setSaving(null);
    }
  };

  const toggleEnabled = async (provider: string, currentEnabled: boolean) => {
    setSaving(provider);

    try {
      const response = await fetch(`http://localhost:8006/llm-settings/${provider}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          is_enabled: !currentEnabled,
        }),
      });

      if (response.ok) {
        await fetchData();
      }
    } catch (error) {
      console.error('Failed to toggle:', error);
    } finally {
      setSaving(null);
    }
  };

  const deleteApiKey = async (provider: string) => {
    if (!confirm('このAPIキーを削除しますか？')) return;

    setSaving(provider);

    try {
      const response = await fetch(`http://localhost:8006/llm-settings/${provider}/api-key`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'APIキーを削除しました' });
        await fetchData();
      }
    } catch (error) {
      setMessage({ type: 'error', text: '削除に失敗しました' });
    } finally {
      setSaving(null);
    }
  };

  const getProviderInfo = (provider: string): LLMProvider | undefined => {
    return providers.find((p) => p.provider === provider);
  };

  const getSetting = (provider: string): LLMSetting | undefined => {
    return settings.find((s) => s.provider === provider);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-muted-foreground">読み込み中...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold">設定</h1>
          <p className="text-sm text-muted-foreground">LLM APIキーとシステム設定</p>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        {/* Message */}
        {message && (
          <div
            className={`mb-6 p-4 rounded-md ${
              message.type === 'success'
                ? 'bg-green-50 text-green-800 border border-green-200'
                : 'bg-red-50 text-red-800 border border-red-200'
            }`}
          >
            {message.text}
          </div>
        )}

        {/* LLM Settings */}
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">LLM プロバイダー設定</h2>
          <p className="text-muted-foreground mb-6">
            ブラウザアクションで使用するLLMのAPIキーを設定します。
            複数のプロバイダーを設定し、デフォルトを選択できます。
          </p>

          <div className="grid gap-4">
            {providers.map((provider) => {
              const setting = getSetting(provider.provider);
              const isEditing = editingProvider === provider.provider;

              return (
                <Card key={provider.provider}>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="flex items-center gap-2">
                          {provider.display_name}
                          {setting?.is_default && (
                            <span className="px-2 py-0.5 text-xs bg-blue-100 text-blue-800 rounded">
                              デフォルト
                            </span>
                          )}
                          {setting?.is_enabled && setting?.has_api_key && (
                            <span className="px-2 py-0.5 text-xs bg-green-100 text-green-800 rounded">
                              有効
                            </span>
                          )}
                        </CardTitle>
                        <p className="text-sm text-muted-foreground mt-1">
                          {provider.description}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        {setting?.has_api_key && (
                          <button
                            onClick={() => toggleEnabled(provider.provider, setting.is_enabled)}
                            disabled={saving === provider.provider}
                            className={`px-3 py-1 text-sm rounded-md transition-colors ${
                              setting.is_enabled
                                ? 'bg-green-100 text-green-800 hover:bg-green-200'
                                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                            }`}
                          >
                            {setting.is_enabled ? 'ON' : 'OFF'}
                          </button>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {isEditing ? (
                      <div className="space-y-4">
                        <div>
                          <label className="block text-sm font-medium mb-1">APIキー</label>
                          <input
                            type="password"
                            value={apiKeyInput}
                            onChange={(e) => setApiKeyInput(e.target.value)}
                            placeholder={setting?.has_api_key ? '（変更しない場合は空欄）' : 'sk-...'}
                            className="w-full px-3 py-2 border rounded-md font-mono text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium mb-1">デフォルトモデル</label>
                          <select
                            value={modelInput || setting?.default_model || ''}
                            onChange={(e) => setModelInput(e.target.value)}
                            className="w-full px-3 py-2 border rounded-md"
                          >
                            {provider.default_models.map((model) => (
                              <option key={model} value={model}>
                                {model}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => saveSetting(provider.provider)}
                            disabled={saving === provider.provider}
                            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 disabled:opacity-50"
                          >
                            {saving === provider.provider ? '保存中...' : '保存'}
                          </button>
                          <button
                            onClick={() => {
                              setEditingProvider(null);
                              setApiKeyInput('');
                              setModelInput('');
                            }}
                            className="px-4 py-2 border rounded-md hover:bg-accent"
                          >
                            キャンセル
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-center gap-4 text-sm">
                          <span className="text-muted-foreground">APIキー:</span>
                          <span className={setting?.has_api_key ? 'text-green-600' : 'text-gray-400'}>
                            {setting?.has_api_key ? '••••••••••••••••' : '未設定'}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-sm">
                          <span className="text-muted-foreground">モデル:</span>
                          <span>{setting?.default_model || provider.default_models[0]}</span>
                        </div>
                        {setting?.last_verified_at && (
                          <div className="flex items-center gap-4 text-sm">
                            <span className="text-muted-foreground">最終検証:</span>
                            <span>{new Date(setting.last_verified_at).toLocaleString('ja-JP')}</span>
                          </div>
                        )}
                        {setting?.last_used_at && (
                          <div className="flex items-center gap-4 text-sm">
                            <span className="text-muted-foreground">最終使用:</span>
                            <span>{new Date(setting.last_used_at).toLocaleString('ja-JP')}</span>
                          </div>
                        )}
                        <div className="flex gap-2 pt-2">
                          <button
                            onClick={() => {
                              setEditingProvider(provider.provider);
                              setModelInput(setting?.default_model || '');
                            }}
                            className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent"
                          >
                            {setting?.has_api_key ? '編集' : 'APIキーを設定'}
                          </button>
                          {setting?.has_api_key && (
                            <>
                              <button
                                onClick={() => verifySetting(provider.provider)}
                                disabled={verifying === provider.provider}
                                className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent disabled:opacity-50"
                              >
                                {verifying === provider.provider ? '検証中...' : '検証'}
                              </button>
                              {!setting.is_default && setting.is_enabled && (
                                <button
                                  onClick={() => setAsDefault(provider.provider)}
                                  disabled={saving === provider.provider}
                                  className="px-3 py-1.5 text-sm border rounded-md hover:bg-accent text-blue-600"
                                >
                                  デフォルトに設定
                                </button>
                              )}
                              <button
                                onClick={() => deleteApiKey(provider.provider)}
                                disabled={saving === provider.provider}
                                className="px-3 py-1.5 text-sm border border-red-200 rounded-md hover:bg-red-50 text-red-600"
                              >
                                削除
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>

        {/* Info Card */}
        <Card>
          <CardHeader>
            <CardTitle>LLM設定について</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              <strong>ブラウザアクション</strong>機能では、LLM（Large Language Model）を使用して
              Webページの内容を理解し、タスクを実行します。
            </p>
            <p>
              <strong>推奨プロバイダー:</strong>
            </p>
            <ul className="list-disc list-inside space-y-1 ml-2">
              <li>
                <strong>Anthropic (Claude)</strong> - 高精度、複雑なタスクに最適
              </li>
              <li>
                <strong>OpenAI (GPT-4o)</strong> - バランスの良い性能
              </li>
              <li>
                <strong>Groq</strong> - 高速推論、シンプルなタスクに最適
              </li>
              <li>
                <strong>Google (Gemini)</strong> - コスト効率が良い
              </li>
            </ul>
            <p>
              <strong>優先順位:</strong> アプリ内設定 &gt; 環境変数 (.env)
            </p>
            <p className="text-yellow-600">
              <strong>注意:</strong> APIキーは暗号化されて保存されますが、
              本番環境では適切なセキュリティ対策を行ってください。
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
