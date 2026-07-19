import os
import subprocess
import unittest
import cv2

from src.trimmer import VideoTrimmer

class TestVideoTrimmer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_path = "test_input.mp4"
        cls.output_path = "test_output.mp4"
        cls.trim_dir = "trim"

        # テスト用の5秒間の動画（映像＋音声）をFFmpegで生成
        # -f lavfi で映像テストソースと音声サイン波を合成
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=5:size=640x480:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
            "-c:v", "libx264",
            "-c:a", "aac",
            cls.input_path
        ]
        
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception as e:
            raise unittest.SkipTest(f"Failed to generate test video using ffmpeg: {e}")

    @classmethod
    def tearDownClass(cls):
        # テスト用ファイルのクリーンアップ
        for path in [cls.input_path, cls.output_path]:
            if os.path.exists(path):
                os.remove(path)
        
        # trimフォルダも存在すれば削除
        trim_out = os.path.join(cls.trim_dir, cls.output_path)
        if os.path.exists(trim_out):
            os.remove(trim_out)
        if os.path.exists(cls.trim_dir):
            os.rmdir(cls.trim_dir)

    def test_trimmer_precision_cut(self):
        # 1.5秒から 3.5秒 (長さ 2.0秒) を切り出し
        start_time = 1.5
        end_time = 3.5
        target_duration = 2.0
        
        output_dest = os.path.join(self.trim_dir, self.output_path)
        
        trimmer = VideoTrimmer(
            input_path=self.input_path,
            output_path=output_dest,
            start_time=start_time,
            end_time=end_time
        )
        
        progresses = []
        def progress_cb(p):
            progresses.append(p)

        # 実行
        trimmer.run(progress_callback=progress_cb)

        # 出力ファイルが存在することを確認
        self.assertTrue(os.path.exists(output_dest))
        # 進捗コールバックが呼ばれ、最後は100%になっていること
        self.assertTrue(len(progresses) > 0)
        self.assertEqual(progresses[-1], 100)

        # 切り出された動画の長さを確認
        cap = cv2.VideoCapture(output_dest)
        self.assertTrue(cap.isOpened())
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = total_frames / fps if fps > 0 else 0.0
        cap.release()

        # 再エンコードされているため、2.0秒の切り出しに対して誤差が極めて小さいことを確認 (許容誤差 0.1秒)
        self.assertAlmostEqual(duration, target_duration, delta=0.1)

if __name__ == "__main__":
    unittest.main()
