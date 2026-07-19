import os
import cv2
import numpy as np

class VideoAnalyzer:
    def __init__(self, video_path, template_dir, mode, orientation, threshold=0.8, sample_rate=1.0):
        """
        映像解析クラス
        :param video_path: 入力動画ファイルパス
        :param template_dir: テンプレート画像が配置されたディレクトリ
        :param mode: 処理モード ('main_after', 'main_only', 'after_only')
        :param orientation: 画面向き ('vertical', 'horizontal')
        :param threshold: マッチングの閾値 (0.0 ~ 1.0)
        :param sample_rate: 1秒間に解析するフレーム数 (例: 1.0 = 1秒に1フレーム)
        """
        self.video_path = video_path
        self.template_dir = template_dir
        self.mode = mode
        self.orientation = orientation
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.total_duration = 0.0

    def _load_and_prepare_template(self, filename, target_size):
        """
        テンプレート画像を読み込み、対象サイズにリサイズして中央1/3領域を切り出す
        """
        path = os.path.join(self.template_dir, filename)
        if not os.path.exists(path):
            print(f"Warning: Template file not found: {path}")
            return None

        # 日本語パス対応のためnp.fromfileで読み込み
        try:
            img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"Error loading template {path}: {e}")
            return None

        if img is None:
            return None

        # 動画の解像度に合わせてリサイズ
        img_resized = cv2.resize(img, target_size)

        # 判定領域を抽出 (縦: 中部1/3, 横: 左半分)
        h, w = target_size[1], target_size[0]
        h_start, h_end = h // 3, 2 * h // 3
        w_start, w_end = 0, w // 2
        template_center = img_resized[h_start:h_end, w_start:w_end]

        return template_center

    def analyze(self, progress_callback=None):
        """
        動画を走査して各待機画面の切り替えタイムスタンプを特定する（探索範囲を最適化）
        """
        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {self.video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        self.total_duration = total_frames / fps if fps > 0 else 0.0
        target_size = (width, height)

        # テンプレートファイルの選択
        prefix = "vert_" if self.orientation == "vertical" else "hor_"
        templates = {
            "start": self._load_and_prepare_template(f"{prefix}start.jpg", target_size),
            "mid": self._load_and_prepare_template(f"{prefix}mid.jpg", target_size),
            "end": self._load_and_prepare_template(f"{prefix}end.jpg", target_size)
        }

        # 判定領域の座標 (縦: 中部1/3, 横: 左半分)
        h_start, h_end = height // 3, 2 * height // 3
        w_start, w_end = 0, width // 2

        # 解析ステップ（秒）
        step_seconds = 1.0 / self.sample_rate

        # 時系列スコア記録用の初期化
        time_series = []
        t = 0.0
        while t <= self.total_duration:
            time_series.append({"time": t, "start": 0.0, "mid": 0.0, "end": 0.0})
            t += step_seconds

        # 探索ウィンドウの定義
        # start: 動画の最初30秒以内
        start_window_limit = 30.0
        # mid, end: 動画終了の6分前（540s）から動画終了までをカバーする
        mid_end_start = max(0.0, self.total_duration - 540.0)
        mid_end_end = self.total_duration

        # 走査対象の時間リストを作成
        start_times = [entry["time"] for entry in time_series if entry["time"] <= start_window_limit]
        mid_end_times = [entry["time"] for entry in time_series if mid_end_start <= entry["time"] <= mid_end_end]

        total_scan_frames = len(start_times) + len(mid_end_times)
        processed_scan_frames = 0

        # パス1: start テンプレートの探索
        consecutive_start_not_detected = 0
        for current_time in start_times:
            frame_idx = int(current_time * fps)
            if frame_idx >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            
            if templates["start"] is not None:
                frame_center = frame[h_start:h_end, w_start:w_end]
                res = cv2.matchTemplate(frame_center, templates["start"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                idx = int(round(current_time / step_seconds))
                if 0 <= idx < len(time_series):
                    time_series[idx]["start"] = max_val

                if max_val < self.threshold:
                    consecutive_start_not_detected += 1
                else:
                    consecutive_start_not_detected = 0

                # 早期打ち切り: startが3秒以上連続して非検出になったら、
                # すでに本編開始したとみなして探索を終了
                if consecutive_start_not_detected >= 3:
                    processed_scan_frames += len(start_times) - start_times.index(current_time) - 1
                    break

            processed_scan_frames += 1
            if progress_callback and total_scan_frames > 0:
                progress_callback(int((processed_scan_frames / total_scan_frames) * 100))

        # パス2: mid, end テンプレートの探索
        consecutive_end_detected = 0
        for current_time in mid_end_times:
            frame_idx = int(current_time * fps)
            if frame_idx >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            
            frame_center = frame[h_start:h_end, w_start:w_end]
            idx = int(round(current_time / step_seconds))

            # mid マッチング
            if templates["mid"] is not None:
                res = cv2.matchTemplate(frame_center, templates["mid"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if 0 <= idx < len(time_series):
                    time_series[idx]["mid"] = max_val

            # end マッチング
            if templates["end"] is not None:
                res = cv2.matchTemplate(frame_center, templates["end"], cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                if 0 <= idx < len(time_series):
                    time_series[idx]["end"] = max_val

                if max_val > self.threshold:
                    consecutive_end_detected += 1
                else:
                    consecutive_end_detected = 0

                # 早期打ち切り: endが1秒以上検出されたら、
                # 終了待機画面に入ったとみなして探索を終了 (endは判定基準を1点に緩和したため)
                if consecutive_end_detected >= 1:
                    processed_scan_frames += len(mid_end_times) - mid_end_times.index(current_time) - 1
                    break

            processed_scan_frames += 1
            if progress_callback and total_scan_frames > 0:
                # 粗い探索の進捗率を最大80%に割り当てる
                progress_callback(int((processed_scan_frames / total_scan_frames) * 80))

        # 判定処理
        results_rough = {
            "main_start": 0.0,
            "main_end": self.total_duration,
            "after_start": 0.0,
            "after_end": self.total_duration
        }

        if not time_series:
            cap.release()
            return results_rough

        # 粗判定ロジックの適用
        results_rough = self._determine_timestamps(time_series, results_rough)
        
        # 第2段階：密探索によるタイムスタンプの精緻化
        results_refined = results_rough.copy()
        
        # 密探索が必要なタスクを抽出して実行
        refine_tasks = []
        # 1. main_start
        if results_rough["main_start"] > 0.0:
            refine_tasks.append(("main_start", "start", True, False))
        # 2. main_end
        if results_rough["main_end"] < self.total_duration:
            temp_key = "mid" if self.mode == "main_after" else "end"
            refine_tasks.append(("main_end", temp_key, False, True))
        # 3. after_start
        if self.mode == "main_after" and results_rough["after_start"] < self.total_duration and results_rough["after_start"] != results_rough["main_end"]:
            refine_tasks.append(("after_start", "mid", True, False))
        elif self.mode == "after_only" and results_rough["after_start"] > 0.0:
            refine_tasks.append(("after_start", "mid", True, False))
        # 4. after_end
        if (self.mode == "main_after" or self.mode == "after_only") and results_rough["after_end"] < self.total_duration:
            refine_tasks.append(("after_end", "end", False, True))

        total_refine = len(refine_tasks)

        for i, (res_key, temp_key, from_det, to_det) in enumerate(refine_tasks):
            rough_val = results_rough[res_key]
            t_refined = self._refine_timestamp(
                cap, fps, total_frames, h_start, h_end, w_start, w_end,
                templates[temp_key], rough_val,
                from_detected=from_det, to_detected=to_det
            )
            results_refined[res_key] = t_refined

            # 密探索の進捗更新 (80% から 98% まで)
            if progress_callback and total_refine > 0:
                p_refine = 80 + int(((i + 1) / total_refine) * 18)
                progress_callback(p_refine)

        cap.release()

        # 安全マージンは適用せず、密探索で得られた正確な遷移点をそのまま結果とする

        if progress_callback:
            progress_callback(100)

        return results_refined

    def _determine_timestamps(self, time_series, default_results):
        """
        時系列スコアから状態遷移を検出し、タイムスタンプを特定する
        """
        results = default_results.copy()
        
        # 判定用ヘルパー：特定のテンプレートが検出状態（スコア > threshold）であるか
        # 誤検出（チャタリング）防止のため、N点連続で状態が維持されたかを判定する
        # sample_rate=1.0の場合、3点連続＝3秒間状態維持
        min_consecutive = 3

        def is_detected_at(index, key):
            if index < 0 or index >= len(time_series):
                return False
            return time_series[index][key] > self.threshold

        def find_state_transition(key, from_detected, to_detected, consecutive_override=None):
            """
            状態遷移（検出状態から非検出、またはその逆）が起こった最初のタイムスタンプを探す
            :param from_detected: 遷移前の状態 (True: 検出, False: 非検出)
            :param to_detected: 遷移後の状態
            """
            n_consec = consecutive_override if consecutive_override is not None else min_consecutive
            for i in range(len(time_series) - n_consec):
                # 現在の状態が from_detected であるかチェック
                current_ok = all(is_detected_at(i - j, key) == from_detected for j in range(n_consec) if i - j >= 0)
                # 以降の状態が to_detected であるかチェック
                future_ok = all(is_detected_at(i + j, key) == to_detected for j in range(1, n_consec + 1))
                
                if current_ok and future_ok:
                    # 遷移の瞬間（i番目とi+1番目の間）の時間を返す
                    return time_series[i + 1]["time"]
            return None

        # 各モードに応じた判定
        if self.mode == "main_after":
            # 1. 本編開始点: startの検出が「終了」した（検出状態 -> 非検出状態）瞬間
            t_main_start = find_state_transition("start", from_detected=True, to_detected=False)
            if t_main_start is not None:
                results["main_start"] = t_main_start
            
            # 2. 本編終了点: midの検出が「開始」した（非検出状態 -> 検出状態）瞬間
            t_main_end = find_state_transition("mid", from_detected=False, to_detected=True)
            if t_main_end is not None:
                results["main_end"] = t_main_end
                
            # 3. AFTER開始点: midの検出が「終了」した（検出状態 -> 非検出状態）瞬間
            t_after_start = find_state_transition("mid", from_detected=True, to_detected=False)
            if t_after_start is not None:
                results["after_start"] = t_after_start
            else:
                # mid検出終了が明示的に見つからない場合は、本編終了点の直後からとする
                results["after_start"] = results["main_end"]

            # 4. AFTER終了点: endの検出が「開始」した（非検出状態 -> 検出状態）瞬間
            # 動画終了の直前に出るため、1点検出で十分と判断して判定を緩和
            t_after_end = find_state_transition("end", from_detected=False, to_detected=True, consecutive_override=1)
            if t_after_end is not None:
                results["after_end"] = t_after_end

        elif self.mode == "main_only":
            # 本編開始点: startの検出が「終了」した瞬間
            t_main_start = find_state_transition("start", from_detected=True, to_detected=False)
            if t_main_start is not None:
                results["main_start"] = t_main_start

            # 本編終了点: endの検出が「開始」した瞬間
            # 終了は最後の最後にあるため、1点検出に判定を緩和
            t_main_end = find_state_transition("end", from_detected=False, to_detected=True, consecutive_override=1)
            if t_main_end is not None:
                results["main_end"] = t_main_end

        elif self.mode == "after_only":
            # AFTER開始点: midの検出が「終了」した瞬間
            t_after_start = find_state_transition("mid", from_detected=True, to_detected=False)
            if t_after_start is not None:
                results["after_start"] = t_after_start

            # AFTER終了点: endの検出が「開始」した瞬間
            # 終了は最後の最後にあるため、1点検出に判定を緩和
            t_after_end = find_state_transition("end", from_detected=False, to_detected=True, consecutive_override=1)
            if t_after_end is not None:
                results["after_end"] = t_after_end

        return results

    def _refine_timestamp(self, cap, fps, total_frames, h_start, h_end, w_start, w_end, 
                          temp_center, rough_time, from_detected, to_detected):
        """
        粗いタイムスタンプの前後2秒をフレーム単位で走査し、正確な遷移時間を特定する
        """
        if temp_center is None:
            return rough_time

        # 探索範囲 [rough_time - 2.0, rough_time + 2.0]
        search_start = max(0.0, rough_time - 2.0)
        search_end = min(self.total_duration, rough_time + 2.0)

        start_frame = int(search_start * fps)
        end_frame = int(search_end * fps)
        
        scores = []

        # 範囲内の全フレームを走査してマッチングスコアを計算
        for f_idx in range(start_frame, end_frame):
            if f_idx >= total_frames:
                break
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_center = frame[h_start:h_end, w_start:w_end]
            res = cv2.matchTemplate(frame_center, temp_center, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            t = f_idx / fps
            scores.append((t, max_val))

        if not scores:
            return rough_time

        # 密判定用：状態が K フレーム維持されたか
        # 30fps動画の場合、遷移は急激なため10フレーム連続（約0.3秒）で十分安定判定可能
        k_consecutive = 10

        def is_detected(score):
            return score > self.threshold

        # 遷移点を見つける
        for i in range(len(scores) - k_consecutive):
            # i点目までが from_detected であるかチェック (過去)
            current_ok = all(is_detected(scores[i - j][1]) == from_detected for j in range(k_consecutive) if i - j >= 0)
            # i+1点目から to_detected であるかチェック (未来)
            future_ok = all(is_detected(scores[i + j][1]) == to_detected for j in range(1, k_consecutive + 1))
            
            if current_ok and future_ok:
                return scores[i + 1][0] # 精確な秒数

        return rough_time
