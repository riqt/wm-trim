# With×MEETS 自動切り出しツール (wm-trim)

本ツールは、With×MEETSの配信録画動画（mp4）から、待機画面のテンプレート画像をベースにした画像認識（テンプレートマッチング）によって、本編およびAFTERの切り替え位置を1フレーム単位の精度で自動検し、高品質に切り出すGUIアプリケーションです。

---

## 📂 ディレクトリの設定 (`config.json`)

本ツールで参照する「動画ファイルのデフォルトフォルダ」や「テンプレート画像のデフォルトフォルダ」は、プロジェクトルートにある `config.json` で個別にカスタマイズできます。

### 1. 設定手順
1. プロジェクトルートにある `config.json.template` をコピーして、同ディレクトリに `config.json` を作成します。
2. `config.json` を開き、お使いの環境に合わせて以下のパスを指定します。

```json
{
  "video_dir": "C:/Path/To/Your/VideoFolder",
  "template_dir": "C:/Path/To/Your/TemplateFolder"
}
```

※ `config.json` はセキュリティ上、および個人環境依存のパスを隠蔽するため、Git管理から自動的に除外（ignore）されています。

### 📷 必要なテンプレート画像
`template_dir` で指定したフォルダ内に、以下の名称で切り替え判定用の画像を配置してください。
1. `start.png` : 開始待機画面（本編開始の検知用）
2. `mid.png` : 中間待機画面（本編終了・AFTER開始の検知用）
3. `end.png` : 終了待機画面（AFTER終了の検知用）

> [!NOTE]
> 判定の干渉を防ぐため、マッチング処理は画面の **「縦方向中央1/3」かつ「横方向左半分」** の領域のみに制限して実行されます。

---

## 🛠️ システム要件

* **OS**: Windows 10/11 (または WSL2 / Linux)
* **Python**: 3.10 以上
* **FFmpeg**: 動画切り出し処理を実行するために、システム環境にインストールされている必要があります。

---

## 🚀 起動方法 (Python環境)

コードのまま実行する場合は、以下の手順でセットアップと起動を行います。

### 1. 依存ライブラリのインストール
プロジェクトのルートディレクトリで以下を実行します。

```bash
pip install -r requirements.txt
```

### 2. アプリケーションの起動
```bash
python src/app.py
```

---

## 📦 実行ファイル (.exe) のビルド方法

Python環境がないPCでも動くスタンドアロンの実行ファイルを作成する場合は、WindowsのコマンドプロンプトまたはPowerShellで以下を実行します。

```bash
# ビルドツールのインストール
pip install pyinstaller

# ビルド実行
pyinstaller --noconsole --onefile --name="WithMeetsTrimmer" src/app.py
```

### ⚠️ exe化の際の注意点 (FFmpegの配置)
ビルドされた `.exe` ファイル単体では、実行するPCの環境変数に `ffmpeg` が通っていないと切り出し保存時にエラーになります。
配布する際は、以下のいずれかでご対応ください。
* **方法A**: 使用するWindowsPCに `ffmpeg` をインストールし、環境変数 (Path) を通す。
* **方法B**: `WithMeetsTrimmer.exe` と **同じフォルダ内** に `ffmpeg.exe` を配置する。（同梱配布）

---

## 🔗 プロジェクト構成

```text
wm-trim/
├── .gitignore             # Git管理から除外する一時ファイル等の設定
├── config.json.template   # ローカル設定用テンプレート (Git追跡対象)
├── config.json            # (ローカル専用) 設定ファイル (Git除外対象)
├── requirements.txt       # 依存ライブラリ一覧
├── README.md              # 本書
├── docs/
│   └── spec.md            # ツールの基本設計・仕様書
├── src/
│   ├── app.py             # GUI画面（PySide6）
│   ├── analyzer.py        # 2段階（粗密）探索・画像解析エンジン
│   └── trimmer.py         # FFmpegによる切り出し保存処理
└── tests/
    └── test_analyzer.py   # 解析エンジンのユニットテスト
```