'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface DashboardStats {
  today: {
    runs: number;
    events_total: number;
    events_success: number;
    events_failed: number;
    pending_approvals: number;
    violations: number;
  };
  timestamp: string;
}

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardStats();
  }, []);

  const fetchDashboardStats = async () => {
    try {
      const response = await fetch('http://localhost:8006/metrics/dashboard');
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Failed to fetch dashboard stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-muted-foreground">読み込み中...</div>
      </div>
    );
  }

  const successRate = stats?.today.events_total
    ? ((stats.today.events_success / stats.today.events_total) * 100).toFixed(1)
    : 0;

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 py-4">
          <h1 className="text-2xl font-bold">SNS運用オーケストレーター</h1>
          <p className="text-sm text-muted-foreground">v1.3.0</p>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h2 className="text-3xl font-bold tracking-tight">ダッシュボード</h2>
          <p className="text-muted-foreground">本日の概要</p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">実行数</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats?.today.runs || 0}</div>
              <p className="text-xs text-muted-foreground">本日のアクティブ実行</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">成功率</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{successRate}%</div>
              <p className="text-xs text-muted-foreground">
                {stats?.today.events_success || 0} / {stats?.today.events_total || 0} イベント
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">承認待ち</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats?.today.pending_approvals || 0}</div>
              <p className="text-xs text-muted-foreground">レビュー待ち</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">違反検知</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-destructive">
                {stats?.today.violations || 0}
              </div>
              <p className="text-xs text-muted-foreground">しきい値超過</p>
            </CardContent>
          </Card>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>クイックアクション</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <a
                href="/runs/create"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent"
              >
                新規実行を作成
              </a>
              <a
                href="/drafts"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent"
              >
                下書きをレビュー
              </a>
              <a
                href="/oauth"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent"
              >
                OAuth接続を管理
              </a>
              <a
                href="/account-generation"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent bg-blue-50 border-blue-200"
              >
                アカウント自動生成
              </a>
              <a
                href="/browser-actions"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent bg-green-50 border-green-200"
              >
                ブラウザアクション (AI自動化)
              </a>
              <a
                href="/settings"
                className="block w-full px-4 py-2 text-sm font-medium text-center border rounded-md hover:bg-accent"
              >
                設定 (LLM APIキー)
              </a>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>システムステータス</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm">APIステータス</span>
                <span className="text-sm font-medium text-green-600">正常稼働中</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">キューステータス</span>
                <span className="text-sm font-medium text-green-600">正常</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm">ワーカーステータス</span>
                <span className="text-sm font-medium text-green-600">実行中</span>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>はじめに</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h3 className="font-semibold mb-2">1. OAuth接続を設定</h3>
                <p className="text-sm text-muted-foreground">
                  YouTube、X (Twitter)、Instagram、TikTokのアカウントを接続します。
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">2. 実行を作成</h3>
                <p className="text-sm text-muted-foreground">
                  投稿、返信、いいね、フォローなどのアクションを設定します。
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">3. AI生成機能を活用</h3>
                <p className="text-sm text-muted-foreground">
                  Claude AIによる投稿・返信案の自動生成が利用できます（承認必須）。
                </p>
              </div>
              <div>
                <h3 className="font-semibold mb-2">4. 監視とレート制限</h3>
                <p className="text-sm text-muted-foreground">
                  16分類の監視システムとレート制限で安全に運用できます。
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>全機能一覧</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <a
                href="/oauth"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">OAuth接続管理</div>
                <div className="text-xs text-muted-foreground">プラットフォーム認証</div>
              </a>
              <a
                href="/account-generation"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">アカウント自動生成</div>
                <div className="text-xs text-muted-foreground">SNSアカウント一括生成</div>
              </a>
              <a
                href="/runs/create"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">実行作成</div>
                <div className="text-xs text-muted-foreground">新規実行設定</div>
              </a>
              <a
                href="/drafts"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">AI下書き</div>
                <div className="text-xs text-muted-foreground">AI生成コンテンツ</div>
              </a>
              <a
                href="/campaigns"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">キャンペーン管理</div>
                <div className="text-xs text-muted-foreground">期間・目標設定</div>
              </a>
              <a
                href="/monitoring"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">監視ダッシュボード</div>
                <div className="text-xs text-muted-foreground">リアルタイム監視</div>
              </a>
              <a
                href="/exports"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">データエクスポート</div>
                <div className="text-xs text-muted-foreground">CSV/JSON出力</div>
              </a>
              <a
                href="/browser-actions"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent bg-green-50"
              >
                <div className="font-semibold">ブラウザアクション</div>
                <div className="text-xs text-muted-foreground">AI駆動ブラウザ自動化</div>
              </a>
              <a
                href="/settings"
                className="block px-4 py-2 text-sm border rounded-md hover:bg-accent"
              >
                <div className="font-semibold">設定</div>
                <div className="text-xs text-muted-foreground">LLM APIキー・システム設定</div>
              </a>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
