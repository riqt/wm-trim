import unittest
from src.analyzer import VideoAnalyzer

class TestVideoAnalyzer(unittest.TestCase):
    def test_determine_timestamps_main_after(self):
        # analyzerインスタンスの作成
        analyzer = VideoAnalyzer(
            video_path="dummy.mp4",
            template_dir="dummy_dir",
            mode="main_after",
            orientation="horizontal",
            threshold=0.8
        )

        # 1秒ごとに1フレーム、計15秒のテストデータ
        time_series = []
        for t in range(16):
            scores = {"time": float(t), "start": 0.1, "mid": 0.1, "end": 0.1}
            if t <= 3:
                scores["start"] = 0.9
            elif 8 <= t <= 10:
                scores["mid"] = 0.9
            elif t >= 13:
                scores["end"] = 0.9
            time_series.append(scores)

        # default
        default_results = {
            "main_start": 0.0,
            "main_end": 15.0,
            "after_start": 0.0,
            "after_end": 15.0
        }
        analyzer.total_duration = 15.0

        # 判定実行
        results = analyzer._determine_timestamps(time_series, default_results)

        # 検証
        self.assertEqual(results["main_start"], 4.0)
        self.assertEqual(results["main_end"], 8.0)
        self.assertEqual(results["after_start"], 11.0)
        self.assertEqual(results["after_end"], 13.0)

    def test_determine_timestamps_main_only(self):
        analyzer = VideoAnalyzer(
            video_path="dummy.mp4",
            template_dir="dummy_dir",
            mode="main_only",
            orientation="horizontal",
            threshold=0.8
        )

        time_series = []
        for t in range(11):
            scores = {"time": float(t), "start": 0.1, "mid": 0.1, "end": 0.1}
            if t <= 2:
                scores["start"] = 0.9
            elif t >= 8:
                scores["end"] = 0.9
            time_series.append(scores)

        default_results = {
            "main_start": 0.0,
            "main_end": 10.0,
            "after_start": 0.0,
            "after_end": 10.0
        }
        analyzer.total_duration = 10.0

        results = analyzer._determine_timestamps(time_series, default_results)

        self.assertEqual(results["main_start"], 3.0)
        self.assertEqual(results["main_end"], 8.0)

    def test_determine_timestamps_after_only(self):
        analyzer = VideoAnalyzer(
            video_path="dummy.mp4",
            template_dir="dummy_dir",
            mode="after_only",
            orientation="horizontal",
            threshold=0.8
        )

        time_series = []
        for t in range(11):
            scores = {"time": float(t), "start": 0.1, "mid": 0.1, "end": 0.1}
            if t <= 2:
                scores["mid"] = 0.9
            elif t >= 8:
                scores["end"] = 0.9
            time_series.append(scores)

        default_results = {
            "main_start": 0.0,
            "main_end": 10.0,
            "after_start": 0.0,
            "after_end": 10.0
        }
        analyzer.total_duration = 10.0

        results = analyzer._determine_timestamps(time_series, default_results)

        self.assertEqual(results["after_start"], 3.0)
        self.assertEqual(results["after_end"], 8.0)

if __name__ == "__main__":
    unittest.main()
