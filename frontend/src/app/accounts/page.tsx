'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface Account {
  id: number;
  task_id: number;
  platform: string;
  username: string;
  email: string;
  password: string;
  phone: string | null;
  proxy_used: string | null;
  verification_status: string;
  status: string;
  created_at: string;
  verified_at: string | null;
  last_login: string | null;
}

const PLATFORM_COLORS = {
  youtube: 'bg-red-100 text-red-800',
  x: 'bg-blue-100 text-blue-800',
  instagram: 'bg-pink-100 text-pink-800',
  tiktok: 'bg-purple-100 text-purple-800',
};

const STATUS_COLORS = {
  active: 'bg-green-100 text-green-800',
  suspended: 'bg-yellow-100 text-yellow-800',
  banned: 'bg-red-100 text-red-800',
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [platformFilter, setPlatformFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copyNotification, setCopyNotification] = useState<string>('');

  useEffect(() => {
    fetchAccounts();
  }, [platformFilter, statusFilter]);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      let url = '/api/account-generation/accounts?limit=1000';
      if (platformFilter) url += `&platform=${platformFilter}`;
      if (statusFilter) url += `&status=${statusFilter}`;

      const response = await fetch(url);
      const data = await response.json();
      setAccounts(data.accounts || []);
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    } finally {
      setLoading(false);
    }
  };

  const filteredAccounts = accounts.filter((account) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      account.username.toLowerCase().includes(query) ||
      account.email.toLowerCase().includes(query) ||
      account.id.toString().includes(query)
    );
  });

  const stats = {
    total: accounts.length,
    youtube: accounts.filter((a) => a.platform === 'youtube').length,
    x: accounts.filter((a) => a.platform === 'x').length,
    instagram: accounts.filter((a) => a.platform === 'instagram').length,
    tiktok: accounts.filter((a) => a.platform === 'tiktok').length,
    active: accounts.filter((a) => a.status === 'active').length,
    suspended: accounts.filter((a) => a.status === 'suspended').length,
    banned: accounts.filter((a) => a.status === 'banned').length,
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const copyToClipboard = (text: string, label: string = 'テキスト') => {
    navigator.clipboard.writeText(text);
    setCopyNotification(`${label}をコピーしました`);
    setTimeout(() => setCopyNotification(''), 3000);
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* コピー通知 */}
      {copyNotification && (
        <div className="fixed top-4 right-4 z-50 bg-green-500 text-white px-6 py-3 rounded-lg shadow-lg animate-fade-in">
          ✓ {copyNotification}
        </div>
      )}

      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">生成済みアカウント一覧</h1>
        <button
          onClick={fetchAccounts}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          更新
        </button>
      </div>

      {/* 統計情報 */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.total}</div>
            <div className="text-sm text-muted-foreground">合計</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-red-600">{stats.youtube}</div>
            <div className="text-sm text-muted-foreground">YouTube</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-blue-600">{stats.x}</div>
            <div className="text-sm text-muted-foreground">X</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-pink-600">{stats.instagram}</div>
            <div className="text-sm text-muted-foreground">Instagram</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-purple-600">{stats.tiktok}</div>
            <div className="text-sm text-muted-foreground">TikTok</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-green-600">{stats.active}</div>
            <div className="text-sm text-muted-foreground">稼働中</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-yellow-600">{stats.suspended}</div>
            <div className="text-sm text-muted-foreground">停止中</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 text-center">
            <div className="text-2xl font-bold text-red-600">{stats.banned}</div>
            <div className="text-sm text-muted-foreground">BAN済</div>
          </CardContent>
        </Card>
      </div>

      {/* フィルター */}
      <Card>
        <CardContent className="p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">検索</label>
              <input
                type="text"
                placeholder="ユーザー名、メール、ID で検索..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">プラットフォーム</label>
              <select
                value={platformFilter}
                onChange={(e) => setPlatformFilter(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">全て</option>
                <option value="youtube">YouTube</option>
                <option value="x">X (Twitter)</option>
                <option value="instagram">Instagram</option>
                <option value="tiktok">TikTok</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">ステータス</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">全て</option>
                <option value="active">稼働中</option>
                <option value="suspended">停止中</option>
                <option value="banned">BAN済</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* アカウント一覧 */}
      <Card>
        <CardHeader>
          <CardTitle>
            アカウント ({filteredAccounts.length} 件)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-8 text-muted-foreground">
              読み込み中...
            </div>
          ) : filteredAccounts.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              アカウントがありません
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">ID</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">タスク</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      プラットフォーム
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      ユーザー名
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      メールアドレス
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      パスワード
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      認証状態
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      ステータス
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      作成日時
                    </th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-gray-600">
                      操作
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filteredAccounts.map((account) => (
                    <tr key={account.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm">{account.id}</td>
                      <td className="px-4 py-3 text-sm">
                        <a
                          href={`/account-generation?task=${account.task_id}`}
                          className="text-blue-600 hover:underline"
                        >
                          #{account.task_id}
                        </a>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-medium uppercase ${
                            PLATFORM_COLORS[account.platform as keyof typeof PLATFORM_COLORS] ||
                            'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {account.platform}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm font-mono">
                        <div className="flex items-center gap-2">
                          <span>{account.username}</span>
                          <button
                            onClick={() => copyToClipboard(account.username, 'ユーザー名')}
                            className="text-gray-400 hover:text-gray-600"
                            title="ユーザー名をコピー"
                          >
                            📋
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm font-mono">
                        <div className="flex items-center gap-2">
                          <span>{account.email}</span>
                          <button
                            onClick={() => copyToClipboard(account.email, 'メールアドレス')}
                            className="text-gray-400 hover:text-gray-600"
                            title="メールアドレスをコピー"
                          >
                            📋
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm font-mono">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-800">{account.password}</span>
                          <button
                            onClick={() => copyToClipboard(account.password, 'パスワード')}
                            className="text-gray-400 hover:text-gray-600"
                            title="パスワードをコピー"
                          >
                            📋
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className="text-xs text-gray-600">
                          {account.verification_status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-medium ${
                            STATUS_COLORS[account.status as keyof typeof STATUS_COLORS] ||
                            'bg-gray-100 text-gray-800'
                          }`}
                        >
                          {account.status === 'active'
                            ? '稼働中'
                            : account.status === 'suspended'
                            ? '停止中'
                            : account.status === 'banned'
                            ? 'BAN済'
                            : account.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {formatDate(account.created_at)}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex gap-2">
                          <button
                            className="text-blue-600 hover:text-blue-800 text-xs"
                            title="詳細"
                          >
                            詳細
                          </button>
                          <button
                            className="text-red-600 hover:text-red-800 text-xs"
                            title="削除"
                          >
                            削除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
