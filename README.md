# Solana Daily Snapshot

Solana DEX の **24h 出来高Top / トレンド / 大口フロー** を 1日3回(JST 00:00 / 08:00 / 16:00)
に画像カードとして Discord と X に自動投稿する bot。テンプレ:
[VirtualNISHI/polymarket-BOT](https://github.com/VirtualNISHI/polymarket-BOT)
の daily-snapshot スタックを Solana 用にデータ層だけ差し替えたもの。

## 何を投稿するか

1200×720 のダーク画像カード(中身は3セクション × 各3行):

- **🔥 Top tokens (24h volume)** — 24h USD 出来高上位、ベーストークンで重複排除
- **⚡ Hot pairs (trending)** — GeckoTerminal の trending feed (24h)
- **🐋 Whale flows (avg $/trade)** — 流動性 $1M+ プールを 1取引あたりUSDで降順
  (USDC/USDT/SOL/WSOL は除外)

各行は `BASE/QUOTE · DEX  $price  ±%24h`。

## 構成

| パス | 役割 |
|---|---|
| `src/solana_client.py` | GeckoTerminal API クライアント (free, no auth) |
| `src/daily_snapshot/collector.py` | 3セクションそれぞれの抽出・dedup ロジック |
| `src/daily_snapshot/job.py` | オーケストレーション(取得→画像→Discord/X→DB保存) |
| `src/daily_snapshot/image_renderer.py` | 1200×720 ダークカード描画 |
| `src/daily_snapshot/formatter.py` | 画像生成失敗時の Discord embed / Tweet テキスト |
| `src/daily_snapshot/jp_translator.py` | 任意の Gemini 日本語化(デフォルトOFF) |
| `src/daily_snapshot/x_client.py` | X v2 ツイート + v1.1 メディアアップロード(tweepy) |
| `src/discord_client.py` | Discord webhook ポスター |
| `src/db.py` | SQLite スキーマ(audit + JP cache) |
| `src/config.py` | settings.yaml + .env ローダー |
| `scripts/run_daily.py` | エントリポイント |
| `scripts/_ci_state.sh` | `bot-state` ブランチに DB を退避(GH Actions 永続化) |
| `.github/workflows/daily-snapshot.yml` | cron 3×/day + workflow_dispatch |
| `config/settings.yaml` | セクション件数・閾値・除外トークンなど |

## データソース

| ソース | エンドポイント | 認証 |
|---|---|---|
| GeckoTerminal | `/networks/solana/pools` (sort=volume / tx_count) | 不要 |
| GeckoTerminal | `/networks/solana/trending_pools` | 不要 |

## セットアップ

### 1. リポジトリ準備

このリポジトリを fork or `git clone` して push する。

### 2. GitHub Secrets 登録

リポジトリ Settings → Secrets and variables → Actions:

| Secret | 必須 | 中身 |
|---|---|---|
| `DISCORD_WEBHOOK_URL` | ✓ | Discord webhook |
| `DAILY_SNAPSHOT_DISCORD_WEBHOOK_URL` | (省略可、↑にfallback) | 別チャンネルにする場合 |
| `X_API_KEY` | ✓ | X Consumer Key |
| `X_API_SECRET` | ✓ | X Consumer Secret |
| `X_ACCESS_TOKEN` | ✓ | X Access Token (Read & write 権限のもの) |
| `X_ACCESS_SECRET` | ✓ | X Access Token Secret |
| `GEMINI_API_KEY` | (任意) | JP翻訳ON時のみ。デフォルト OFF |
| `ANTHROPIC_API_KEY` | (任意) | JP翻訳プロバイダーを anthropic にする場合のみ |

### 3. 動作確認

Actions タブ → "daily-snapshot" → "Run workflow" で `dry_run: true` 実行 →
ログで画像生成成功を確認。問題なければ `dry_run: false` で再実行。

### 4. スケジュール

`.github/workflows/daily-snapshot.yml` の cron (UTC):

```yaml
- cron: '5 15 * * *'  # 00:05 JST
- cron: '5 23 * * *'  # 08:05 JST
- cron: '5 7 * * *'   # 16:05 JST
```

## ローカル実行

```bash
pip install -e .
cp .env.example .env  # 値を埋める
python scripts/run_daily.py --dry-run    # 投稿せず画像生成のみ
python scripts/run_daily.py              # 本投稿
python scripts/run_daily.py --no-x       # Discord のみ
```

## カスタマイズ

`config/settings.yaml` で:
- セクション件数 (`top_tokens_count` 等、3が前提)
- 出来高フィルタ (`min_volume_24h_usd`)
- Whale 閾値 (`whale_min_volume_24h_usd`, `whale_exclude_base_tokens`)
- 表示用エイリアス (`display_aliases`)

`src/daily_snapshot/image_renderer.py` で:
- セクション見出しの絵文字・タイトル
- 画像サイズ (`W, H = 1200, 720`)
- カラーパレット (`BG`, `CARD`, `GREEN`, `RED` …)

## トラブルシューティング

- **GeckoTerminal 429**: free tier で 30 req/min。1日3回の本ジョブなら通常問題なし。
- **X 403 Forbidden**: アプリ権限が Read only。Developer Portal で Read & write
  に変更後、Access Token を **必ず再生成**。
- **画像が日本語で豆腐(□)**: `fonts-noto-cjk` がインストールされているか確認
  (workflow には含めてある)。
- **Whale flows が空**: `whale_min_volume_24h_usd` を下げるか、
  `whale_exclude_base_tokens` から SOL を外す。
