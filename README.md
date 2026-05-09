# 📚 雑誌発売日カレンダー通知

楽天ブックス API で雑誌の発売日を取得し、iPhone カレンダーに自動通知を届けるシステムです。  
GitHub Actions が毎朝 JST 8:00 に `calendar.ics` を更新。iPhone のカレンダー購読機能で自動同期します。

## 通知のタイミング

| タイミング | 通知内容 |
|---|---|
| 発売前日 21:00 | 📚 [雑誌名] 発売日(明日) |
| 発売当日 08:00 | 📚 [雑誌名] 本日発売 - 楽天で購入（URLリンク付き）|

---

## セットアップ手順

### Step 1 — 楽天アプリIDの取得

1. [楽天 Developers](https://webservice.rakuten.co.jp/) にアクセスしてログイン
2. 「アプリ ID 発行」→「新しいアプリを作成」
3. アプリ名・概要を入力して送信
4. 表示された **アプリ ID（applicationId）** をコピーして控えておく

### Step 2 — リポジトリの作成とコードのプッシュ

```bash
# このディレクトリで Git 初期化
git init
git add .
git commit -m "feat: initial setup"

# GitHub に新しいリポジトリを作成（例: magazine-calendar）
# ※ Public でも Private でも動作します
git remote add origin https://github.com/YOUR_USERNAME/magazine-calendar.git
git push -u origin main
```

### Step 3 — GitHub Secrets に楽天アプリIDを登録

1. GitHub リポジトリページ → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** をクリック
3. 以下の通り入力して **Add secret**

   | Name | Value |
   |---|---|
   | `RAKUTEN_APP_ID` | （Step 1 で取得したアプリ ID） |

### Step 4 — GitHub Actions の有効化確認

1. リポジトリ → **Actions** タブを開く
2. 「I understand my workflows, go ahead and enable them」が表示された場合はクリックして有効化
3. **Update Magazine Calendar** ワークフローが表示されていれば OK

### Step 5 — calendar.ics の初回生成（手動実行）

1. **Actions** → **Update Magazine Calendar** → **Run workflow** ボタンをクリック
2. 完了後、リポジトリのルートに `calendar.ics` がコミットされていることを確認

以降は毎日 JST 08:00 に自動実行されます。

### Step 6 — iPhone でカレンダーを購読登録

#### 購読 URL の確認

```
https://raw.githubusercontent.com/YOUR_USERNAME/magazine-calendar/main/calendar.ics
```

> **プライベートリポジトリの場合**  
> raw URL は認証が必要なため、直接購読できません。  
> 代わりに GitHub Pages を有効化して公開するか、リポジトリを Public に設定してください。

#### iPhone での登録手順

**方法 A（ブラウザから）**

1. iPhone の Safari で以下の URL を開く（`https://` を `webcal://` に変えてアクセス）:

   ```
   webcal://raw.githubusercontent.com/YOUR_USERNAME/magazine-calendar/main/calendar.ics
   ```

2. 「カレンダーを登録」のダイアログが表示されたら **「続ける」** をタップ
3. カレンダーアプリが開いたら **「登録」** をタップ

**方法 B（設定アプリから）**

1. **設定** → **カレンダー** → **アカウント** → **アカウントを追加**
2. **その他** → **照会するカレンダーを追加**
3. サーバー欄に以下の URL を入力して **次へ**:

   ```
   https://raw.githubusercontent.com/YOUR_USERNAME/magazine-calendar/main/calendar.ics
   ```

4. **保存** をタップ

#### 同期間隔の設定（任意）

設定 → カレンダー → **データのフェッチ** で「プッシュ」または最短間隔に設定すると、
更新がより早く反映されます。

---

## 監視対象の雑誌を変更する

`magazines.yaml` を編集してコミット・プッシュするだけです。

```yaml
magazines:
  - title: "週刊少年ジャンプ"

  # JAN コードを指定すると検索精度が向上します
  - title: "BRUTUS"
    jan: "4910064690640"

  - title: "Newton"
```

変更後、Actions を手動実行するか翌朝の自動実行を待つと `calendar.ics` が更新されます。

---

## ファイル構成

```
.
├── magazines.yaml              # 監視対象の雑誌リスト
├── notifier.py                 # メインスクリプト
├── requirements.txt            # Python 依存パッケージ
├── calendar.ics                # 生成されるカレンダーファイル（自動更新）
└── .github/
    └── workflows/
        └── daily.yml           # GitHub Actions ワークフロー
```

---

## ローカルでのテスト実行

```bash
pip install -r requirements.txt
export RAKUTEN_APP_ID="your_app_id_here"
python notifier.py
```

実行後、`calendar.ics` が生成されます。ファイルをダブルクリックすると Mac の カレンダー.app で内容を確認できます。

---

## トラブルシューティング

### 雑誌が見つからない / イベントが追加されない

- 楽天ブックスでの正式タイトルと一致しているか確認（`title` フィールド）
- 楽天ブックスの [雑誌カテゴリ](https://books.rakuten.co.jp/search/?g=004) で検索して正確な名称を確認
- JAN コードが分かれば `jan` フィールドに設定すると精度が上がります

### iPhone でアラームが鳴らない

iOS では**購読カレンダーの VALARM（アラーム）は動作しない制限**がある場合があります（iOS バージョンによって異なります）。  
カレンダーイベント自体は表示されるため、個別のイベントを長押し → 「イベントを編集」→ 「アラーム」で手動追加することもできます。

### GitHub Actions が失敗する

- Secrets に `RAKUTEN_APP_ID` が正しく登録されているか確認
- Actions タブのログで `API error` または `Request failed` のメッセージを確認
- 楽天 API の [利用制限](https://webservice.rakuten.co.jp/guide/throttle)（1 秒 1 リクエスト）に準拠しています

---

## 技術仕様

- **API**: [楽天ブックス雑誌検索 API](https://webservice.rakuten.co.jp/documentation/books-magazine-search)
- **カバー期間**: 実行日から過去 14 日〜未来 60 日
- **iCalendar**: RFC 5545 準拠、UTF-8、CRLF 改行
- **VALARM トリガー**: 全日イベントの DTSTART（JST 0:00）からの相対時刻
  - 前日 21:00 JST → `TRIGGER;RELATED=START:-PT3H`
  - 当日 08:00 JST → `TRIGGER;RELATED=START:PT8H`
# magazine-project
