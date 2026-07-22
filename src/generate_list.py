import os
import sys
import json
import re

def load_config():
    """config.jsonから設定情報をロードする"""
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"),
        os.path.join(os.path.dirname(__file__), "config.json"),
        "config.json"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load config at {path}: {e}")
    return {"video_dir": ""}

def main():
    config = load_config()
    video_dir = config.get("video_dir", "")

    # コマンドライン引数でディレクトリが直接渡された場合はそちらを優先
    if len(sys.argv) > 1:
        video_dir = sys.argv[1]

    if not video_dir or not os.path.exists(video_dir):
        print(f"Error: 動画フォルダが存在しないか、設定されていません: '{video_dir}'")
        print("Usage: python src/generate_list.py [対象フォルダのパス]")
        sys.exit(1)

    print(f"動画フォルダを検索中: {video_dir}")

    # 日付パターンの正規表現 (YYYY-MM-DD または YYYY-M-DD)
    date_pattern = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")

    categories = {
        "incl_after": [],
        "after": [],
        "other": []
    }

    for root, dirs, files in os.walk(video_dir):
        # 'trim' フォルダ配下は検索から除外
        if os.path.basename(root).lower() == "trim":
            continue

        for file in files:
            if file.endswith(".mp4") and date_pattern.search(file):
                full_path = os.path.abspath(os.path.join(root, file))
                
                # カテゴリ分類
                if "(incl after)" in file or "incl agter" in file:
                    categories["incl_after"].append(full_path)
                elif "-after" in file:
                    categories["after"].append(full_path)
                else:
                    categories["other"].append(full_path)

    # 出力用ディレクトリの作成
    output_dir = os.path.abspath("lists")
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n【分類結果】")
    chunk_size = 10
    total_created_files = 0

    for cat_name, file_list in categories.items():
        file_list.sort()
        count = len(file_list)
        print(f"・{cat_name}: 計 {count} 件")

        # 10個ずつのチャンクに分割してファイル出力
        for i in range(0, count, chunk_size):
            chunk = file_list[i:i + chunk_size]
            part_num = (i // chunk_size) + 1
            filename = f"{cat_name}_part{part_num:02d}.txt"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                for path in chunk:
                    f.write(path + "\n")

            total_created_files += 1

    print(f"\n生成完了: `lists/` ディレクトリ内に 10 個ずつのテキストファイル（計 {total_created_files} ファイル）を出力しました。")
    print(f"出力先: {output_dir}")

if __name__ == "__main__":
    main()
