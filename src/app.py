import sys
import os
import re
import cv2
import json
from PySide6.QtCore import Qt, QUrl, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, QDoubleSpinBox, QSpinBox,
    QProgressBar, QMessageBox, QGroupBox, QStyle
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from analyzer import VideoAnalyzer
from trimmer import VideoTrimmer


class AnalysisThread(QThread):
    progress = Signal(int)
    finished_analysis = Signal(dict)
    error = Signal(str)

    def __init__(self, video_path, template_dir, mode, orientation, threshold):
        super().__init__()
        self.video_path = video_path
        self.template_dir = template_dir
        self.mode = mode
        self.orientation = orientation
        self.threshold = threshold

    def run(self):
        try:
            analyzer = VideoAnalyzer(
                video_path=self.video_path,
                template_dir=self.template_dir,
                mode=self.mode,
                orientation=self.orientation,
                threshold=self.threshold,
                sample_rate=1.0  # 1秒間に1フレーム解析
            )
            
            def update_progress(p):
                self.progress.emit(p)
                
            results = analyzer.analyze(progress_callback=update_progress)
            self.finished_analysis.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class TrimmingThread(QThread):
    progress = Signal(int)
    finished_trim = Signal()
    error = Signal(str)

    def __init__(self, trimmers):
        super().__init__()
        self.trimmers = trimmers

    def run(self):
        try:
            total = len(self.trimmers)
            for i, trimmer in enumerate(self.trimmers):
                def update_progress(p):
                    # 全体の進捗率を計算 (各トリマーの進捗を等分に反映)
                    overall = int((i * 100 + p) / total)
                    self.progress.emit(overall)
                
                trimmer.run(progress_callback=update_progress)
            
            self.finished_trim.emit()
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("With×MEETS 自動切り出しツール")
        self.resize(1100, 700)

        # 状態保持用変数
        self.video_path = ""
        self.total_duration = 0.0
        self.fps = 30.0
        self.is_slider_pressed = False

        # 設定ファイル読み込み
        self.config_data = self._load_config()
        
        # UI構築
        self._init_ui()
        self._init_player()

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
    return {"video_dir": "", "template_dir": ""}


def auto_detect_settings(file_path):
    """動画ファイル名と動画メタデータから、モード、向き、総再生時間、fpsを判定する"""
    filename = os.path.basename(file_path)
    
    # 1. 処理モード自動判定
    if "(incl after)" in filename or "incl agter" in filename:
        mode_idx = 0  # main_after
        mode_key = "main_after"
    elif "-after" in filename:
        mode_idx = 2  # after_only
        mode_key = "after_only"
    else:
        mode_idx = 1  # main_only
        mode_key = "main_only"

    # 2. 画面の向き・動画メタデータ自動判定
    orient_idx = 0
    orient_key = "vertical"
    total_duration = 0.0
    fps = 30.0
    width = 0
    height = 0

    cap = cv2.VideoCapture(file_path)
    if cap.isOpened():
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_val = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        total_duration = frames / fps_val if fps_val > 0 else 0.0
        fps = fps_val if fps_val > 0 else 30.0
        
        if width < height:
            orient_idx = 0  # vertical
            orient_key = "vertical"
        else:
            orient_idx = 1  # horizontal
            orient_key = "horizontal"
        cap.release()

    return {
        "mode_idx": mode_idx,
        "mode_key": mode_key,
        "orient_idx": orient_idx,
        "orient_key": orient_key,
        "total_duration": total_duration,
        "fps": fps,
        "width": width,
        "height": height
    }


def process_single_video(video_path, template_dir):
    """単一の動画ファイルを解析・トリミング保存する"""
    if not os.path.exists(video_path):
        print(f"Error: 動画ファイルが存在しません: {video_path}")
        return False

    print(f"\n----------------------------------------")
    print(f"処理対象: {video_path}")

    # パラメータ自動判別
    info = auto_detect_settings(video_path)
    print(f"判定結果 - モード: {info['mode_key']}, 向き: {info['orient_key']}, 解像度: {info['width']}x{info['height']}")

    # 解析実行
    print("動画を解析中...")
    threshold = 0.80
    analyzer = VideoAnalyzer(
        video_path=video_path,
        template_dir=template_dir,
        mode=info["mode_key"],
        orientation=info["orient_key"],
        threshold=threshold,
        sample_rate=1.0
    )

    last_progress = [-1]
    def print_analysis_progress(p):
        if p % 10 == 0 and p != last_progress[0]:
            print(f"解析進捗: {p}%")
            last_progress[0] = p

    results = analyzer.analyze(progress_callback=print_analysis_progress)
    print("解析完了。切り出しタイムスタンプ:")
    for k, v in results.items():
        print(f"  {k}: {v:.2f} 秒")

    # 切り出し保存準備
    input_dir = os.path.dirname(os.path.abspath(video_path))
    trim_dir = os.path.join(input_dir, "trim")
    filename = os.path.basename(video_path)

    date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", filename)
    if date_match:
        date_str = date_match.group(1)
    else:
        date_str, _ = os.path.splitext(filename)

    trimmers = []
    mode_key = info["mode_key"]

    if mode_key in ["main_after", "main_only"]:
        start = results["main_start"]
        end = results["main_end"]
        if start < end:
            output_name = f"{date_str}-main-trim.mp4"
            output_path = os.path.join(trim_dir, output_name)
            trimmers.append(VideoTrimmer(video_path, output_path, start, end))
        else:
            print("Warning: 本編の開始位置が終了位置以上のためスキップします。")

    if mode_key in ["main_after", "after_only"]:
        start = results["after_start"]
        end = results["after_end"]
        if start < end:
            output_name = f"{date_str}-after-trim.mp4"
            output_path = os.path.join(trim_dir, output_name)
            trimmers.append(VideoTrimmer(video_path, output_path, start, end))
        else:
            print("Warning: AFTERの開始位置が終了位置以上のためスキップします。")

    if not trimmers:
        print("Error: 有効なトリミング対象が存在しませんでした。")
        return False

    # FFmpeg切り出し実行
    print("FFmpegで切り出し保存を開始します...")
    total_trimmers = len(trimmers)
    for i, trimmer in enumerate(trimmers):
        print(f"[{i+1}/{total_trimmers}] 保存先: {trimmer.output_path}")
        last_trim_p = [-1]
        def print_trim_progress(p):
            if p % 20 == 0 and p != last_trim_p[0]:
                print(f"  切り出し進捗: {p}%")
                last_trim_p[0] = p
        trimmer.run(progress_callback=print_trim_progress)

    print("処理完了。")
    return True


def run_cli(input_path):
    """CLIモードで自動で解析およびカット・保存を実行する (単一動画またはtxtファイルリストに対応)"""
    if not os.path.exists(input_path):
        print(f"Error: 入力ファイルが存在しません: {input_path}")
        sys.exit(1)

    # 設定読み込み
    config_data = load_config()
    template_dir = config_data.get("template_dir", "")
    if not template_dir or not os.path.exists(template_dir):
        print(f"Error: テンプレートフォルダが存在しませんまたは指定されていません: {template_dir}")
        sys.exit(1)

    # テキストファイル (.txt) が指定された場合
    if input_path.lower().endswith(".txt"):
        print(f"=== WM-Trim CLI バッチモード開始 ===")
        print(f"リストファイル: {input_path}")

        video_paths = []
        with open(input_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    video_paths.append(line)

        total_videos = len(video_paths)
        print(f"対象動画数: {total_videos} 件")

        success_count = 0
        for idx, video_path in enumerate(video_paths, 1):
            print(f"\n========================================")
            print(f" Progress: [{idx} / {total_videos}]")
            print(f"========================================")
            if process_single_video(video_path, template_dir):
                success_count += 1

        print(f"\n=== 全バッチ処理完了: {success_count}/{total_videos} 件 成功 ===")

    else:
        print(f"=== WM-Trim CLI モード開始 ===")
        process_single_video(input_path, template_dir)
        print("=== 完了 ===")



class AnalysisThread(QThread):
    progress = Signal(int)
    finished_analysis = Signal(dict)
    error = Signal(str)

    def __init__(self, video_path, template_dir, mode, orientation, threshold):
        super().__init__()
        self.video_path = video_path
        self.template_dir = template_dir
        self.mode = mode
        self.orientation = orientation
        self.threshold = threshold

    def run(self):
        try:
            analyzer = VideoAnalyzer(
                video_path=self.video_path,
                template_dir=self.template_dir,
                mode=self.mode,
                orientation=self.orientation,
                threshold=self.threshold,
                sample_rate=1.0  # 1秒間に1フレーム解析
            )
            
            def update_progress(p):
                self.progress.emit(p)
                
            results = analyzer.analyze(progress_callback=update_progress)
            self.finished_analysis.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class TrimmingThread(QThread):
    progress = Signal(int)
    finished_trim = Signal()
    error = Signal(str)

    def __init__(self, trimmers):
        super().__init__()
        self.trimmers = trimmers

    def run(self):
        try:
            total = len(self.trimmers)
            for i, trimmer in enumerate(self.trimmers):
                def update_progress(p):
                    # 全体の進捗率を計算 (各トリマーの進捗を等分に反映)
                    overall = int((i * 100 + p) / total)
                    self.progress.emit(overall)
                
                trimmer.run(progress_callback=update_progress)
            
            self.finished_trim.emit()
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("With×MEETS 自動切り出しツール")
        self.resize(1100, 700)

        # 状態保持用変数
        self.video_path = ""
        self.total_duration = 0.0
        self.fps = 30.0
        self.is_slider_pressed = False

        # 設定ファイル読み込み
        self.config_data = load_config()
        
        # UI構築
        self._init_ui()
        self._init_player()

    def _init_ui(self):
        # メインレイアウト
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # 左側コントロールパネル
        left_panel = QVBoxLayout()
        main_layout.addLayout(left_panel, stretch=2)

        # 右側プレイヤーパネル
        right_panel = QVBoxLayout()
        main_layout.addLayout(right_panel, stretch=3)

        # ----------------------------------------------------
        # 左側：ファイル選択・設定
        # ----------------------------------------------------
        # 入力ファイル選択
        file_group = QGroupBox("入力動画ファイル選択")
        file_layout = QHBoxLayout(file_group)
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        self.file_browse_btn = QPushButton("参照...")
        self.file_browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(self.file_path_edit)
        file_layout.addWidget(self.file_browse_btn)
        left_panel.addWidget(file_group)

        # 解析設定
        config_group = QGroupBox("解析パラメータ設定")
        config_layout = QVBoxLayout(config_group)

        # テンプレート画像ディレクトリ
        temp_dir_layout = QHBoxLayout()
        temp_dir_layout.addWidget(QLabel("テンプレートフォルダ:"))
        self.temp_dir_edit = QLineEdit(self.config_data.get("template_dir", ""))
        self.temp_dir_browse_btn = QPushButton("参照...")
        self.temp_dir_browse_btn.clicked.connect(self._browse_template_dir)
        temp_dir_layout.addWidget(self.temp_dir_edit)
        temp_dir_layout.addWidget(self.temp_dir_browse_btn)
        config_layout.addLayout(temp_dir_layout)

        # モード選択
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("処理モード:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "本編 ＋ AFTER (main_after)",
            "本編のみ (main_only)",
            "AFTERのみ (after_only)"
        ])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        config_layout.addLayout(mode_layout)

        # 画面向き
        orient_layout = QHBoxLayout()
        orient_layout.addWidget(QLabel("画面の向き:"))
        self.orientation_combo = QComboBox()
        self.orientation_combo.addItems(["縦画面 (vertical)", "横画面 (horizontal)"])
        orient_layout.addWidget(self.orientation_combo)
        config_layout.addLayout(orient_layout)

        # マッチング閾値
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("検出類似度閾値 (0.0~1.0):"))
        self.thresh_spin = QDoubleSpinBox()
        self.thresh_spin.setRange(0.1, 1.0)
        self.thresh_spin.setSingleStep(0.05)
        self.thresh_spin.setValue(0.80)
        thresh_layout.addWidget(self.thresh_spin)
        config_layout.addLayout(thresh_layout)

        # 解析ボタン
        self.analyze_btn = QPushButton("動画解析開始")
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.clicked.connect(self._start_analysis)
        config_layout.addWidget(self.analyze_btn)
        
        left_panel.addWidget(config_group)

        # タイムスタンプ微調整
        self.adjust_group = QGroupBox("切り出しタイムスタンプ微調整 (分・秒)")
        self.adjust_group.setEnabled(False)
        adjust_layout = QVBoxLayout(self.adjust_group)

        # 各タイムスタンプのスピンボックスとプレビューボタン
        self.ts_widgets = {}
        for ts_key, ts_label in [
            ("main_start", "本編 開始位置:"),
            ("main_end", "本編 終了位置:"),
            ("after_start", "AFTER 開始位置:"),
            ("after_end", "AFTER 終了位置:")
        ]:
            row = QHBoxLayout()
            row.addWidget(QLabel(ts_label))
            
            # 分スピンボックス
            spin_min = QSpinBox()
            spin_min.setRange(0, 999)
            spin_min.setSuffix(" 分")
            row.addWidget(spin_min)
            
            # 秒スピンボックス
            spin_sec = QDoubleSpinBox()
            spin_sec.setRange(0.0, 59.99)
            spin_sec.setDecimals(2)
            spin_sec.setSingleStep(1.0)
            spin_sec.setSuffix(" 秒")
            row.addWidget(spin_sec)
            
            # プレビューボタン
            preview_btn = QPushButton("プレビュー")
            preview_btn.clicked.connect(lambda checked=False, key=ts_key: self._preview_timestamp(key))
            row.addWidget(preview_btn)

            # 位置取得ボタン
            set_btn = QPushButton("位置取得")
            set_btn.clicked.connect(lambda checked=False, key=ts_key: self._set_timestamp_from_current(key))
            row.addWidget(set_btn)
            
            adjust_layout.addLayout(row)
            self.ts_widgets[ts_key] = {
                "spin_min": spin_min,
                "spin_sec": spin_sec,
                "set_btn": set_btn,
                "layout": row,
                "label": row.itemAt(0).widget()
            }

        left_panel.addWidget(self.adjust_group)

        # 保存ボタン
        self.save_btn = QPushButton("切り出し保存実行")
        self.save_btn.setEnabled(False)
        self.save_btn.setStyleSheet("font-weight: bold; background-color: #2e7d32; color: white;")
        self.save_btn.clicked.connect(self._start_trimming)
        left_panel.addWidget(self.save_btn)

        # 進捗バー・ステータス
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        left_panel.addWidget(self.progress_bar)
        
        self.status_label = QLabel("動画ファイルを選択してください。")
        self.status_label.setWordWrap(True)
        left_panel.addWidget(self.status_label)

        # ----------------------------------------------------
        # 右側：プレイヤー
        # ----------------------------------------------------
        # 動画描画エリア
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: black;")
        right_panel.addWidget(self.video_widget, stretch=1)

        # プレイヤーコントローラー
        play_ctrl_layout = QHBoxLayout()

        # 1フレーム戻すボタン
        self.rewind_btn = QPushButton("◀ 1フレーム")
        self.rewind_btn.clicked.connect(self._rewind_1frame)
        play_ctrl_layout.addWidget(self.rewind_btn)

        # 再生・一時停止
        self.play_btn = QPushButton()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.clicked.connect(self._play_pause)
        play_ctrl_layout.addWidget(self.play_btn)

        # 1フレーム進めるボタン
        self.forward_btn = QPushButton("1フレーム ▶")
        self.forward_btn.clicked.connect(self._forward_1frame)
        play_ctrl_layout.addWidget(self.forward_btn)

        # 再生位置シーカー
        from PySide6.QtWidgets import QSlider
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._set_media_position)
        play_ctrl_layout.addWidget(self.slider)

        # 時間表示
        self.time_label = QLabel("00:00 / 00:00")
        play_ctrl_layout.addWidget(self.time_label)

        right_panel.addLayout(play_ctrl_layout)

    def _init_player(self):
        # プレイヤー初期化
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # シグナル紐付け
        self.media_player.positionChanged.connect(self._on_player_position_changed)
        self.media_player.durationChanged.connect(self._on_player_duration_changed)

    # ----------------------------------------------------
    # UIイベントハンドラ
    # ----------------------------------------------------
    def _browse_file(self):
        initial_dir = self.config_data.get("video_dir", "")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "動画ファイルを開く", initial_dir, "動画ファイル (*.mp4 *.mkv)"
        )
        if file_path:
            self.video_path = file_path
            self.file_path_edit.setText(file_path)
            
            # 動画情報を読み込んで自動判定
            info = auto_detect_settings(file_path)
            self.mode_combo.setCurrentIndex(info["mode_idx"])
            self.orientation_combo.setCurrentIndex(info["orient_idx"])
            self.total_duration = info["total_duration"]
            self.fps = info["fps"]

            if info["width"] > 0 and info["height"] > 0:
                self.status_label.setText(f"動画読込完了: {info['width']}x{info['height']}, 長さ: {self._format_time(self.total_duration)}")
            else:
                self.status_label.setText("動画ファイルのメタデータ取得に失敗しました。")
            
            # メディアプレイヤーにセット
            self.media_player.setSource(QUrl.fromLocalFile(file_path))
            self.analyze_btn.setEnabled(True)

    def _browse_template_dir(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "テンプレートフォルダを選択", self.temp_dir_edit.text()
        )
        if dir_path:
            self.temp_dir_edit.setText(dir_path)

    def _on_mode_changed(self, index):
        # 選択したモードに応じて、微調整スピンボックスの表示・非表示を制御
        # index: 0=main_after, 1=main_only, 2=after_only
        self._update_adjust_ui_state(index)

    def _get_ts_value(self, key):
        """分・秒スピンボックスから合計秒数を取得"""
        minutes = self.ts_widgets[key]["spin_min"].value()
        seconds = self.ts_widgets[key]["spin_sec"].value()
        return minutes * 60.0 + seconds

    def _set_ts_value(self, key, total_seconds):
        """合計秒数から分・秒スピンボックスを設定"""
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        self.ts_widgets[key]["spin_min"].setValue(minutes)
        self.ts_widgets[key]["spin_sec"].setValue(seconds)

    def _update_adjust_ui_state(self, mode_idx):
        # 各分スピンボックスの最大値を動画の長さに合わせる
        total_mins = int(self.total_duration // 60) if self.total_duration > 0 else 999
        for key, w_dict in self.ts_widgets.items():
            w_dict["spin_min"].setMaximum(total_mins)

        # 有効・無効切り替え
        show_main = (mode_idx == 0 or mode_idx == 1)
        show_after = (mode_idx == 0 or mode_idx == 2)

        for key in ["main_start", "main_end"]:
            self.ts_widgets[key]["spin_min"].setEnabled(show_main)
            self.ts_widgets[key]["spin_sec"].setEnabled(show_main)
            self.ts_widgets[key]["set_btn"].setEnabled(show_main)
            self.ts_widgets[key]["label"].setEnabled(show_main)
            
        for key in ["after_start", "after_end"]:
            self.ts_widgets[key]["spin_min"].setEnabled(show_after)
            self.ts_widgets[key]["spin_sec"].setEnabled(show_after)
            self.ts_widgets[key]["set_btn"].setEnabled(show_after)
            self.ts_widgets[key]["label"].setEnabled(show_after)

    # ----------------------------------------------------
    # 解析処理フロー
    # ----------------------------------------------------
    def _start_analysis(self):
        # 必要なパラメータ取得
        template_dir = self.temp_dir_edit.text()
        
        mode_idx = self.mode_combo.currentIndex()
        mode_map = {0: "main_after", 1: "main_only", 2: "after_only"}
        mode = mode_map[mode_idx]

        orient_idx = self.orientation_combo.currentIndex()
        orient = "vertical" if orient_idx == 0 else "horizontal"

        threshold = self.thresh_spin.value()

        if not os.path.exists(template_dir):
            QMessageBox.warning(self, "エラー", f"テンプレートフォルダが存在しません:\n{template_dir}")
            return

        # UI無効化
        self.analyze_btn.setEnabled(False)
        self.file_browse_btn.setEnabled(False)
        self.temp_dir_browse_btn.setEnabled(False)
        self.mode_combo.setEnabled(False)
        self.orientation_combo.setEnabled(False)
        self.thresh_spin.setEnabled(False)
        self.adjust_group.setEnabled(False)
        self.save_btn.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText("動画を解析中... (1秒1フレームで粗探索後、遷移点付近をフレーム単位で密探索しています)")

        # スレッド起動
        self.analysis_thread = AnalysisThread(
            video_path=self.video_path,
            template_dir=template_dir,
            mode=mode,
            orientation=orient,
            threshold=threshold
        )
        self.analysis_thread.progress.connect(self.progress_bar.setValue)
        self.analysis_thread.finished_analysis.connect(self._on_analysis_finished)
        self.analysis_thread.error.connect(self._on_analysis_error)
        self.analysis_thread.start()

    @Slot(dict)
    def _on_analysis_finished(self, results):
        self.status_label.setText("解析完了。切り出しタイミングを確認し、微調整を行ってください。")
        self.progress_bar.setValue(100)

        # UI復帰
        self.file_browse_btn.setEnabled(True)
        self.temp_dir_browse_btn.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.orientation_combo.setEnabled(True)
        self.thresh_spin.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.adjust_group.setEnabled(True)
        self.save_btn.setEnabled(True)

        # 結果をスピンボックスにセット
        for key, val in results.items():
            self._set_ts_value(key, val)

        # スピンボックスの有効無効の再更新
        self._update_adjust_ui_state(self.mode_combo.currentIndex())

    @Slot(str)
    def _on_analysis_error(self, err_msg):
        QMessageBox.critical(self, "解析エラー", f"解析処理中にエラーが発生しました:\n{err_msg}")
        self.status_label.setText("解析エラーが発生しました。")
        
        # UI復帰
        self.file_browse_btn.setEnabled(True)
        self.temp_dir_browse_btn.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.orientation_combo.setEnabled(True)
        self.thresh_spin.setEnabled(True)
        self.analyze_btn.setEnabled(True)

    # ----------------------------------------------------
    # 切り出し・保存処理フロー
    # ----------------------------------------------------
    def _start_trimming(self):
        # 1. 保存先ディレクトリとファイル名の決定
        # 保存場所: 入力されたWith×MEETSファイルと同一ディレクトリ内に `trim` フォルダ
        input_dir = os.path.dirname(self.video_path)
        trim_dir = os.path.join(input_dir, "trim")
        filename = os.path.basename(self.video_path)

        # 日付部分の抽出 (YYYY-MM-DD または YYYY-M-DD)
        date_match = re.search(r"(\d{4}-\d{1,2}-\d{1,2})", filename)
        if date_match:
            date_str = date_match.group(1)
        else:
            # 日付が見つからない場合は拡張子を除いたファイル名を使用
            date_str, _ = os.path.splitext(filename)

        # トリマーオブジェクトの作成リスト
        trimmers = []
        mode_idx = self.mode_combo.currentIndex()

        if mode_idx == 0 or mode_idx == 1:  # main_after または main_only
            start = self._get_ts_value("main_start")
            end = self._get_ts_value("main_end")
            if start >= end:
                QMessageBox.warning(self, "入力エラー", "本編の開始位置が終了位置以上になっています。")
                return
            
            output_name = f"{date_str}-main-trim.mp4"
            output_path = os.path.join(trim_dir, output_name)
            trimmers.append(VideoTrimmer(self.video_path, output_path, start, end))

        if mode_idx == 0 or mode_idx == 2:  # main_after または after_only
            start = self._get_ts_value("after_start")
            end = self._get_ts_value("after_end")
            if start >= end:
                QMessageBox.warning(self, "入力エラー", "AFTERの開始位置が終了位置以上になっています。")
                return
            
            output_name = f"{date_str}-after-trim.mp4"
            output_path = os.path.join(trim_dir, output_name)
            trimmers.append(VideoTrimmer(self.video_path, output_path, start, end))

        if not trimmers:
            return

        # UI無効化
        self.file_browse_btn.setEnabled(False)
        self.temp_dir_browse_btn.setEnabled(False)
        self.mode_combo.setEnabled(False)
        self.orientation_combo.setEnabled(False)
        self.thresh_spin.setEnabled(False)
        self.analyze_btn.setEnabled(False)
        self.adjust_group.setEnabled(False)
        self.save_btn.setEnabled(False)

        self.progress_bar.setValue(0)
        self.status_label.setText("FFmpegで切り出し保存を実行中... (再エンコードを伴うため時間がかかります)")

        # スレッド起動
        self.trimming_thread = TrimmingThread(trimmers)
        self.trimming_thread.progress.connect(self.progress_bar.setValue)
        self.trimming_thread.finished_trim.connect(self._on_trimming_finished)
        self.trimming_thread.error.connect(self._on_trimming_error)
        self.trimming_thread.start()

    @Slot()
    def _on_trimming_finished(self):
        self.status_label.setText("切り出し保存が正常に完了しました！")
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "完了", "動画の切り出し保存が完了しました。")

        # UI復帰
        self.file_browse_btn.setEnabled(True)
        self.temp_dir_browse_btn.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.orientation_combo.setEnabled(True)
        self.thresh_spin.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.adjust_group.setEnabled(True)
        self.save_btn.setEnabled(True)

    @Slot(str)
    def _on_trimming_error(self, err_msg):
        QMessageBox.critical(self, "保存エラー", f"切り出し保存中にエラーが発生しました:\n{err_msg}")
        self.status_label.setText("保存中にエラーが発生しました。")
        
        # UI復帰
        self.file_browse_btn.setEnabled(True)
        self.temp_dir_browse_btn.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.orientation_combo.setEnabled(True)
        self.thresh_spin.setEnabled(True)
        self.analyze_btn.setEnabled(True)
        self.adjust_group.setEnabled(True)
        self.save_btn.setEnabled(True)

    # ----------------------------------------------------
    # プレイヤー制御
    # ----------------------------------------------------
    def _play_pause(self):
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.media_player.play()
            self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def _set_timestamp_from_current(self, ts_key):
        # 現在のプレイヤー位置(ms)を取得し、スピンボックスに反映
        position_ms = self.media_player.position()
        current_seconds = position_ms / 1000.0
        self._set_ts_value(ts_key, current_seconds)
        self.status_label.setText(f"現在の再生位置 {self._format_time(current_seconds)} をセットしました。")

    def _preview_timestamp(self, ts_key):
        seconds = self._get_ts_value(ts_key)
        # ミリ秒に変換してシーク
        self.media_player.setPosition(int(seconds * 1000))
        # プレビュー時は自動再生せず一時停止する
        self.media_player.pause()
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def _rewind_1frame(self):
        current_pos = self.media_player.position()
        step = int(1000.0 / self.fps) if self.fps > 0 else 33
        new_pos = max(0, current_pos - step)
        self.media_player.setPosition(new_pos)

    def _forward_1frame(self):
        current_pos = self.media_player.position()
        duration = self.media_player.duration()
        step = int(1000.0 / self.fps) if self.fps > 0 else 33
        new_pos = min(duration, current_pos + step)
        self.media_player.setPosition(new_pos)

    def _on_slider_pressed(self):
        self.is_slider_pressed = True

    def _on_slider_released(self):
        self.is_slider_pressed = False
        self._set_media_position(self.slider.value())

    def _set_media_position(self, value):
        # スライダー(0~1000)から再生位置への変換
        if self.media_player.duration() > 0:
            pos_ms = int((value / 1000.0) * self.media_player.duration())
            self.media_player.setPosition(pos_ms)

    def _on_player_position_changed(self, position_ms):
        # ユーザーがスライダーを操作中でない場合のみ同期する
        if not self.is_slider_pressed:
            duration_ms = self.media_player.duration()
            if duration_ms > 0:
                val = int((position_ms / float(duration_ms)) * 1000)
                # 再帰シグナルの競合を避けるために一時的にシグナルをブロック
                self.slider.blockSignals(True)
                self.slider.setValue(val)
                self.slider.blockSignals(False)
        
        duration_ms = self.media_player.duration()
        self.time_label.setText(
            f"{self._format_time(position_ms / 1000.0)} / {self._format_time(duration_ms / 1000.0)}"
        )

    def _on_player_duration_changed(self, duration_ms):
        # メディア切り替え時に総時間を更新
        self.time_label.setText(f"00:00 / {self._format_time(duration_ms / 1000.0)}")

    # ----------------------------------------------------
    # ユーティリティ
    # ----------------------------------------------------
    def _format_time(self, total_seconds):
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
        else:
            return f"{minutes:02d}:{seconds:05.2f}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg_path = sys.argv[1]
        # 引数が指定されている場合（オプションパラメータフラグ除く）はCLIモードで実行
        if not arg_path.startswith("-"):
            run_cli(arg_path)
            sys.exit(0)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

