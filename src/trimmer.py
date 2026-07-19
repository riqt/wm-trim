import os
import subprocess
import re

class VideoTrimmer:
    def __init__(self, input_path, output_path, start_time, end_time):
        """
        FFmpegによる再エンコード切り出しを行うクラス
        :param input_path: 入力動画ファイルパス
        :param output_path: 出力動画ファイルパス
        :param start_time: 切り出し開始位置（秒）
        :param end_time: 切り出し終了位置（秒）
        """
        self.input_path = input_path
        self.output_path = output_path
        self.start_time = max(0.0, start_time)
        self.end_time = end_time
        self.duration = max(0.0, end_time - start_time)

    def run(self, progress_callback=None):
        """
        切り出しを実行する（ブロッキング処理）
        :param progress_callback: 進捗更新用コールバック関数 (0 ~ 100)
        """
        # 出力先ディレクトリの自動作成
        output_dir = os.path.dirname(self.output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # FFmpegコマンドの構築
        # -ss と -t を入力ファイルの前に置くことで高速にシークさせつつ、正確に再エンコード
        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{self.start_time:.3f}",
            "-t", f"{self.duration:.3f}",
            "-i", self.input_path,
            "-c:v", "libx264",
            "-crf", "18",
            "-preset", "veryfast",
            "-c:a", "aac",
            self.output_path
        ]

        print(f"Executing: {' '.join(cmd)}")

        # FFmpegの実行
        # stdout/stderrをパイプして、進捗パースに利用する
        # Windows/Linux共に動作するように startupinfo などは特に指定しない
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1,
            encoding="utf-8"
        )

        # time=00:00:00.00 形式の出力をキャプチャするための正規表現
        time_pattern = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

        # 標準エラー出力を1行ずつ読み込んで進捗をパース
        while True:
            # readlineは改行までブロックする
            line = process.stderr.readline()
            if not line and process.poll() is not None:
                break

            if not line:
                continue

            match = time_pattern.search(line)
            if match and progress_callback and self.duration > 0:
                hours = int(match.group(1))
                minutes = int(match.group(2))
                seconds = float(match.group(3))
                current_seconds = hours * 3600 + minutes * 60 + seconds
                
                # パーセンテージの計算 (100%を超えないように丸める)
                progress = min(100, int((current_seconds / self.duration) * 100))
                progress_callback(progress)

        # パイプをクローズしてリソースを解放
        process.stdout.close()
        process.stderr.close()

        # プロセスの終了コードを確認
        return_code = process.poll()
        if return_code != 0:
            # エラー詳細を取得
            error_output = process.stderr.read()
            raise RuntimeError(
                f"FFmpeg failed with exit code {return_code}.\n"
                f"Command: {' '.join(cmd)}\n"
                f"Error Log:\n{error_output}"
            )

        if progress_callback:
            progress_callback(100)
