import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger

from app.log import logger
from app.core.config import settings
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.utils.http import RequestUtils


class ChdTaskMonitor(_PluginBase):
    plugin_name = "CHD任务监控"
    plugin_desc = "抓取CHD任务页面进度与任务人数，并按规则发送通知。"
    plugin_icon = "statistic.png"
    plugin_version = "1.1.0"
    plugin_author = "jonysun"
    author_url = "https://github.com/jonysun"
    plugin_config_prefix = "chdtaskmonitor_"
    plugin_order = 99
    auth_level = 1

    _enabled: bool = False
    _cookie: str = ""
    _check_cron: str = "*/30 * * * *"
    _daily_notify_time: str = "09:00"
    _notify_on_capacity_available: bool = True
    _notify_daily_progress: bool = True
    _capacity_threshold: int = 200
    _capacity_alert_max_times: int = 3
    _capacity_alert_cooldown_hours: int = 1
    _reset_capacity_alert_state: bool = False
    _enable_task_chart: bool = False
    _show_chart_in_dashboard: bool = False
    _task_type: str = "Extreme"
    _dashboard_size: str = "half"
    _dashboard_min_height: int = 220
    _onlyonce: bool = False

    _last_capacity_below: bool = False
    _capacity_alert_sent_times: int = 0
    _last_capacity_alert_ts: float = 0.0
    _last_cookie_alert_day: str = ""
    _last_error_alert_day: str = ""
    _last_snapshot: Dict[str, Any] = {}
    _last_poll_ts: float = 0.0

    _url: str = "https://ptchdbits.co/selfassess.php"
    _chart_url: str = "https://ptchdbits.co/selfassessinfo.php"
    _TASK_TARGETS: Dict[str, Dict[str, float]] = {
        "Master": {"upload": 2000.0, "download": 600.0, "seeding": 45000.0},
        "Ultimate": {"upload": 1500.0, "download": 500.0, "seeding": 40000.0},
        "Extreme": {"upload": 1000.0, "download": 400.0, "seeding": 35000.0},
        "Veteran": {"upload": 500.0, "download": 300.0, "seeding": 30000.0},
        "Insane": {"upload": 300.0, "download": 100.0, "seeding": 20000.0},
    }
    _SIZE_COLS: Dict[str, Dict[str, int]] = {
        "one_third": {"cols": 12, "md": 4},
        "half": {"cols": 12, "md": 6},
        "two_third": {"cols": 12, "md": 8},
        "full": {"cols": 12},
    }

    _ua: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = self.__to_bool(config.get("enabled"), False)
            self._cookie = str(config.get("cookie") or "").strip()
            self._check_cron = str(config.get("check_cron") or "*/30 * * * *").strip()
            self._daily_notify_time = str(config.get("daily_notify_time") or "09:00").strip()
            self._notify_on_capacity_available = self.__to_bool(config.get("notify_on_capacity_available"), True)
            self._notify_daily_progress = self.__to_bool(config.get("notify_daily_progress"), True)
            self._capacity_threshold = self.__safe_int(config.get("capacity_threshold"), 200, 1, 9999)
            self._capacity_alert_max_times = self.__safe_int(config.get("capacity_alert_max_times"), 3, 1, 99)
            self._capacity_alert_cooldown_hours = self.__safe_int(config.get("capacity_alert_cooldown_hours"), 1, 1, 168)
            self._reset_capacity_alert_state = self.__to_bool(config.get("reset_capacity_alert_state"), False)
            self._enable_task_chart = self.__to_bool(config.get("enable_task_chart"), False)
            self._show_chart_in_dashboard = self.__to_bool(config.get("show_chart_in_dashboard"), False)
            self._task_type = str(config.get("task_type") or "Extreme")
            if self._task_type not in self._TASK_TARGETS:
                self._task_type = "Extreme"
            self._dashboard_size = str(config.get("dashboard_size") or "half")
            if self._dashboard_size not in self._SIZE_COLS:
                self._dashboard_size = "half"
            self._dashboard_min_height = self.__safe_int(config.get("dashboard_min_height"), 220, 160, 520)
            self._onlyonce = self.__to_bool(config.get("onlyonce"), False)

        if self._reset_capacity_alert_state:
            self.__reset_capacity_alert_runtime_state()
            self._reset_capacity_alert_state = False
            self.__persist_config()

        if self._onlyonce:
            self._run_polling()
            self._onlyonce = False
            self.__persist_config()

        if self._enabled:
            logger.info(
                "[chdtaskmonitor] config loaded: check_cron=%s daily_notify_time=%s notify_capacity=%s notify_daily=%s",
                self._check_cron,
                self._daily_notify_time,
                self._notify_on_capacity_available,
                self._notify_daily_progress,
            )

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []

        services: List[Dict[str, Any]] = []
        try:
            services.append({
                "id": "ChdTaskPolling",
                "name": "CHD任务轮询",
                "trigger": CronTrigger.from_crontab(self._check_cron),
                "func": self._run_polling,
                "kwargs": {},
            })
            logger.info("[chdtaskmonitor] register polling cron: %s", self._check_cron)
        except Exception:
            logger.warning("[chdtaskmonitor] check_cron 非法，使用默认 */30 * * * *")
            services.append({
                "id": "ChdTaskPolling",
                "name": "CHD任务轮询",
                "trigger": CronTrigger.from_crontab("*/30 * * * *"),
                "func": self._run_polling,
                "kwargs": {},
            })
            logger.info("[chdtaskmonitor] register polling cron: */30 * * * *")

        if self._notify_daily_progress:
            hour, minute = self.__parse_hhmm(self._daily_notify_time)
            services.append({
                "id": "ChdTaskDailySummary",
                "name": "CHD任务日报",
                "trigger": CronTrigger(hour=hour, minute=minute),
                "func": self._run_daily_summary,
                "kwargs": {},
            })
            logger.info("[chdtaskmonitor] register daily summary time: %02d:%02d", hour, minute)

        return services

    def _run_polling(self):
        now_ts = datetime.now().timestamp()
        # guard against duplicated scheduler trigger storms
        if self._last_poll_ts and (now_ts - self._last_poll_ts) < 20:
            logger.info("[chdtaskmonitor] polling skipped by guard window")
            return
        self._last_poll_ts = now_ts

        parsed = self._fetch_and_parse(source="polling")
        if not parsed:
            logger.info("[chdtaskmonitor] polling skipped: parse_result=None")
            return

        if not self._notify_on_capacity_available:
            logger.info("[chdtaskmonitor] capacity notify disabled")
            return

        # If user already has an active task, don't send slot-available alerts.
        if parsed.get("has_task"):
            logger.info("[chdtaskmonitor] capacity alert skipped: active task exists")
            return

        population = parsed.get("population")
        if self._should_send_capacity_alert(population=population):
            logger.info(
                "[chdtaskmonitor] capacity alert trigger: population=%s threshold=%s sent=%s/%s",
                population,
                self._capacity_threshold,
                self._capacity_alert_sent_times,
                self._capacity_alert_max_times,
            )
            self.post_message(
                mtype=NotificationType.SiteMessage,
                title="【CHD任务监控】任务名额提醒",
                text=(
                    f"任务系统当前人数：{population}，已低于阈值 {self._capacity_threshold}。\n"
                    f"已发送名额提醒：{self._capacity_alert_sent_times}/{self._capacity_alert_max_times}"
                    f"（达到上限后静默 {self._capacity_alert_cooldown_hours} 小时，或人数恢复后重置）"
                ),
            )
            logger.info("[chdtaskmonitor] capacity alert sent")
        else:
            logger.info(
                "[chdtaskmonitor] capacity alert not sent: population=%s sent=%s/%s",
                population,
                self._capacity_alert_sent_times,
                self._capacity_alert_max_times,
            )

    def _run_daily_summary(self):
        if not self._notify_daily_progress:
            return

        parsed = self._fetch_and_parse(source="daily")
        if not parsed:
            logger.info("[chdtaskmonitor] daily summary skipped: parse_result=None")
            return

        logger.info("[chdtaskmonitor] daily summary trigger")
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【CHD任务监控】今日任务进度",
            text=(
                f"剩余时间：{parsed.get('countdown', '未解析到')}\n"
                f"上传量：{parsed.get('upload', '未解析到')}\n"
                f"下载量：{parsed.get('download', '未解析到')}\n"
                f"做种积分：{parsed.get('seeding', '未解析到')}\n"
                f"任务系统当前人数：{parsed.get('population', '未解析到')}"
            ),
        )
        logger.info("[chdtaskmonitor] daily summary sent")

    def _fetch_and_parse(self, source: str = "manual") -> Optional[Dict[str, Any]]:
        html = self._fetch_selfassess_html(source=source)
        if not html:
            self.__notify_error_once_per_day("请求任务页面失败，请检查网络或Cookie。")
            return None

        if not self._is_authenticated_page(html):
            self.__notify_cookie_issue_once_per_day()
            return None

        parsed = self._parse_task_page(html)
        parsed["task_status"] = self.__build_task_status(parsed)

        if parsed.get("has_task") and self._enable_task_chart:
            chart_html = self._fetch_selfassessinfo_html(source=source)
            if chart_html:
                parsed["chart"] = self._parse_task_chart(chart_html)
            else:
                parsed["chart"] = None
        else:
            parsed["chart"] = None
        self._last_snapshot = {
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **parsed,
        }
        logger.info(
            "[chdtaskmonitor] parsed source=%s countdown=%s upload=%s download=%s seeding=%s population=%s has_task=%s chart=%s",
            source,
            parsed.get("countdown"),
            parsed.get("upload"),
            parsed.get("download"),
            parsed.get("seeding"),
            parsed.get("population"),
            parsed.get("has_task"),
            "yes" if parsed.get("chart") else "no",
        )
        return parsed

    def _fetch_selfassess_html(self, source: str = "manual") -> Optional[str]:
        if not self._cookie:
            return None
        try:
            response = RequestUtils(
                cookies=self._cookie,
                headers={"User-Agent": self._ua},
            ).get_res(url=self._url)
            if response and response.status_code == 200:
                logger.info("[chdtaskmonitor] page fetch ok: source=%s status=200 via cookies param", source)
                return response.text

            # fallback: some environments require explicit Cookie header string
            response = RequestUtils(
                headers={
                    "User-Agent": self._ua,
                    "Cookie": self._cookie,
                }
            ).get_res(url=self._url)
            if response and response.status_code == 200:
                logger.info("[chdtaskmonitor] page fetch ok: source=%s status=200 via Cookie header", source)
                return response.text

            logger.warning(
                "[chdtaskmonitor] 请求失败 source=%s status=%s",
                source,
                response.status_code if response else "None",
            )
            return None
        except Exception as err:
            logger.error("[chdtaskmonitor] 请求异常: %s", str(err))
            return None

    def _fetch_selfassessinfo_html(self, source: str = "manual") -> Optional[str]:
        if not self._cookie:
            return None
        try:
            response = RequestUtils(
                cookies=self._cookie,
                headers={"User-Agent": self._ua},
            ).get_res(url=self._chart_url)
            if response and response.status_code == 200:
                logger.info("[chdtaskmonitor] chart fetch ok: source=%s status=200 via cookies param", source)
                return response.text

            response = RequestUtils(
                headers={
                    "User-Agent": self._ua,
                    "Cookie": self._cookie,
                }
            ).get_res(url=self._chart_url)
            if response and response.status_code == 200:
                logger.info("[chdtaskmonitor] chart fetch ok: source=%s status=200 via Cookie header", source)
                return response.text

            logger.warning(
                "[chdtaskmonitor] chart fetch failed source=%s status=%s",
                source,
                response.status_code if response else "None",
            )
            return None
        except Exception as err:
            logger.error("[chdtaskmonitor] chart fetch exception: %s", str(err))
            return None

    def _is_authenticated_page(self, html: str) -> bool:
        if not html:
            return False
        has_user_marker = ("欢迎回来" in html) or ("logout.php" in html) or ("退出" in html)
        has_task_marker = ("任务系统当前人数" in html) or ("您领取的任务距离结束还有" in html)
        return has_user_marker and has_task_marker

    def _parse_task_page(self, html: str) -> Dict[str, Any]:
        text = self.__html_to_text(html)

        # Focus parse around the task progress block to avoid header/footer noise.
        focus_html = html
        marker = html.find("您领取的任务距离结束还有")
        if marker >= 0:
            end_candidates = []
            for token in ["规则：", "<table cellspacing=\"0\" cellpadding=\"10\" width=\"80%\"", "<img width=\"300\" src='./pic/tasklogo5.png'", "<iframe src=\"./selfassessinfo.php\""]:
                pos = html.find(token, marker)
                if pos > marker:
                    end_candidates.append(pos)
            end_at = min(end_candidates) if end_candidates else min(len(html), marker + 12000)
            focus_html = html[marker:end_at]

        focus_text = self.__html_to_text(focus_html)

        countdown_match = re.search(r"您领取的任务距离结束还有\s*([0-9]+\s*天\s*[0-9]+\s*小时\s*[0-9]+\s*分钟\s*[0-9]+\s*秒)", focus_text)
        upload_match = re.search(r"上传量[:：]\s*(.*?)\s*[（\(]增量[）\)]", focus_html, flags=re.S)
        download_match = re.search(r"下载量[:：]\s*(.*?)\s*[（\(]增量[）\)]", focus_html, flags=re.S)
        seeding_match = re.search(r"做种积分[:：]\s*(.*?)\s*[（\(]增量[）\)]", focus_html, flags=re.S)

        population_match = re.search(r"任务系统当前人数[:：]\s*(\d+)\s*人", text)
        if not population_match:
            population_match = re.search(r"任务系统当前人数[:：]\s*(\d+)\s*人", html)

        countdown = self.__clean_text(countdown_match.group(1)) if countdown_match else "未解析到"
        if countdown.startswith("00 天 00 小时 00 分钟") or countdown.startswith("0 天 0 小时 0 分钟"):
            computed = self.__compute_countdown_from_script(html)
            if computed:
                countdown = computed

        has_task = bool(countdown_match or upload_match or download_match or seeding_match)
        if not has_task:
            countdown = "当前无任务"

        return {
            "countdown": countdown,
            "upload": self.__extract_progress_line(upload_match, "上传量"),
            "download": self.__extract_progress_line(download_match, "下载量"),
            "seeding": self.__extract_progress_line(seeding_match, "做种积分"),
            "population": int(population_match.group(1)) if population_match else None,
            "has_task": has_task,
        }

    def __extract_progress_line(self, matched: Optional[re.Match], label: str) -> str:
        if not matched:
            return "未解析到"
        content = self.__clean_text(self.__html_to_text(matched.group(1)))
        if not content:
            return "未解析到"
        return f"{content}（增量）"

    def __build_task_status(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        task_type = self._task_type if self._task_type in self._TASK_TARGETS else "Extreme"
        targets = self._TASK_TARGETS.get(task_type) or self._TASK_TARGETS["Extreme"]

        upload_text = str(parsed.get("upload") or "")
        download_text = str(parsed.get("download") or "")
        seeding_text = str(parsed.get("seeding") or "")

        upload_progress, upload_done = self.__progress_from_text(upload_text, targets["upload"], mode="data")
        download_progress, download_done = self.__progress_from_text(download_text, targets["download"], mode="data")
        seeding_progress, seeding_done = self.__progress_from_text(seeding_text, targets["seeding"], mode="score")

        return {
            "task_type": task_type,
            "items": [
                {"key": "upload", "label": "上传量", "text": upload_text or "未解析到", "progress": upload_progress, "done": upload_done},
                {"key": "download", "label": "下载量", "text": download_text or "未解析到", "progress": download_progress, "done": download_done},
                {"key": "seeding", "label": "做种积分", "text": seeding_text or "未解析到", "progress": seeding_progress, "done": seeding_done},
            ],
        }

    @staticmethod
    def __parse_data_to_gb(raw: str) -> Optional[float]:
        matched = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(TB|GB|MB|KB)", str(raw or ""), flags=re.I)
        if not matched:
            return None
        value = float(matched.group(1))
        unit = matched.group(2).upper()
        if unit == "TB":
            return value * 1024.0
        if unit == "GB":
            return value
        if unit == "MB":
            return value / 1024.0
        if unit == "KB":
            return value / (1024.0 * 1024.0)
        return None

    @staticmethod
    def __parse_number(raw: str) -> Optional[float]:
        matched = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(raw or ""))
        if not matched:
            return None
        return float(matched.group(1))

    def __progress_from_text(self, text: str, target: float, mode: str) -> Tuple[float, bool]:
        if not text or target <= 0:
            return 0.0, False
        if any(word in text for word in ["已通过", "已完成", "完成", "达成"]):
            return 1.0, True
        if "还需要" in text:
            remain = self.__parse_data_to_gb(text) if mode == "data" else self.__parse_number(text)
            if remain is None:
                return 0.0, False
            progress = max(0.0, min(1.0, (target - remain) / target))
            return progress, progress >= 0.999
        return 0.0, False

    def _parse_task_chart(self, html: str) -> Optional[Dict[str, Any]]:
        try:
            categories_match = re.search(r"categories\s*:\s*\[([^\]]*)\]", html, flags=re.S)
            if not categories_match:
                logger.warning("[chdtaskmonitor] chart parse failed: categories missing")
                return None
            categories = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", categories_match.group(1))]
            categories = [str(x).strip() for x in categories if str(x).strip()]

            series_list: List[Dict[str, Any]] = []
            for block in re.finditer(r"\{\s*name\s*:\s*'([^']+)'[\s\S]*?data\s*:\s*\[([^\]]*)\]", html, flags=re.S):
                name = block.group(1).strip()
                raw_data = block.group(2)
                data: List[float] = []
                for token in raw_data.split(","):
                    token = token.strip()
                    if not token:
                        continue
                    try:
                        data.append(float(token))
                    except Exception:
                        continue
                if not data:
                    continue

                color = "#9155FD"
                if "做种" in name:
                    color = "#FF0000"
                elif "上传" in name:
                    color = "#00A8FF"
                elif "下载" in name:
                    color = "#43A047"
                series_list.append({"name": name, "data": data, "color": color})

            if not series_list:
                logger.warning("[chdtaskmonitor] chart parse failed: series missing")
                return None

            logger.info("[chdtaskmonitor] chart parse ok: categories=%s series=%s", len(categories), len(series_list))
            return {"categories": categories, "series": series_list}
        except Exception as err:
            logger.warning("[chdtaskmonitor] chart parse exception: %s", str(err))
            return None

    @staticmethod
    def __build_chart_component(chart: Optional[Dict[str, Any]], height: int = 220) -> Optional[dict]:
        if not isinstance(chart, dict):
            return None
        categories = chart.get("categories") or []
        series = chart.get("series") or []
        if not categories or not series:
            return None
        return {
            "component": "VApexChart",
            "props": {
                "height": height,
                "options": {
                    "chart": {"type": "line", "toolbar": {"show": False}},
                    "stroke": {"curve": "smooth", "width": 2},
                    "xaxis": {"categories": categories, "labels": {"show": True}},
                    "legend": {"show": True, "position": "top"},
                    "dataLabels": {"enabled": False},
                    "tooltip": {"shared": True, "intersect": False},
                    "grid": {"borderColor": "#9CA3AF33", "strokeDashArray": 3},
                },
                "series": series,
            },
        }

    @staticmethod
    def __progress_color(value: str) -> str:
        text = str(value or "")
        if any(mark in text for mark in ["已通过", "已完成", "完成", "达成"]):
            return "#43A047"
        if any(mark in text for mark in ["还需要", "未完成", "不足", "未达成"]):
            return "#E53935"
        return "#FFFFFF"

    @staticmethod
    def __compute_countdown_from_script(html: str) -> str:
        matched = re.search(r"downCount\s*\(\s*\{\s*date\s*:\s*'([^']+)'", html)
        if not matched:
            return ""
        try:
            target = datetime.strptime(matched.group(1), "%m/%d/%Y %H:%M:%S")
            now = datetime.now()
            if target <= now:
                return "00 天 00 小时 00 分钟 00 秒"
            total_seconds = int((target - now).total_seconds())
            days = total_seconds // 86400
            rem = total_seconds % 86400
            hours = rem // 3600
            rem = rem % 3600
            minutes = rem // 60
            seconds = rem % 60
            return f"{days:02d} 天 {hours:02d} 小时 {minutes:02d} 分钟 {seconds:02d} 秒"
        except Exception:
            return ""

    def _should_send_capacity_alert(self, population: Optional[int]) -> bool:
        if population is None:
            return False

        below = population < self._capacity_threshold
        if not below:
            self.__reset_capacity_alert_runtime_state()
            return False

        now_ts = datetime.now().timestamp()
        cooldown_seconds = self._capacity_alert_cooldown_hours * 3600

        # cooldown release while still below threshold
        if self._capacity_alert_sent_times >= self._capacity_alert_max_times and self._last_capacity_alert_ts > 0:
            if (now_ts - self._last_capacity_alert_ts) >= cooldown_seconds:
                self._capacity_alert_sent_times = 0
                self._last_capacity_below = False

        if not self._last_capacity_below:
            self._last_capacity_below = True
            self._capacity_alert_sent_times = 1
            self._last_capacity_alert_ts = now_ts
            return True

        if self._capacity_alert_sent_times < self._capacity_alert_max_times:
            self._capacity_alert_sent_times += 1
            self._last_capacity_alert_ts = now_ts
            return True

        return False

    def __reset_capacity_alert_runtime_state(self):
        self._last_capacity_below = False
        self._capacity_alert_sent_times = 0
        self._last_capacity_alert_ts = 0.0

    @staticmethod
    def __html_to_text(html: str) -> str:
        no_script = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
        no_style = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", no_script, flags=re.I)
        no_tag = re.sub(r"<[^>]+>", " ", no_style)
        return re.sub(r"\s+", " ", no_tag).strip()

    @staticmethod
    def __clean_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip(" .。\n\r\t")

    @staticmethod
    def __safe_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            number = int(value)
            return max(min_value, min(max_value, number))
        except Exception:
            return default

    @staticmethod
    def __to_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def __parse_hhmm(value: str) -> Tuple[int, int]:
        raw = str(value or "").strip()
        matched = re.match(r"^(\d{1,2}):(\d{1,2})$", raw)
        if not matched:
            return 9, 0
        hour = int(matched.group(1))
        minute = int(matched.group(2))
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return 9, 0
        return hour, minute

    def __notify_cookie_issue_once_per_day(self):
        today_key = datetime.now().strftime("%Y-%m-%d")
        if self._last_cookie_alert_day == today_key:
            return
        self._last_cookie_alert_day = today_key
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【CHD任务监控】Cookie失效",
            text="未检测到有效登录态，请检查插件中的CHD Cookie。",
        )

    def __notify_error_once_per_day(self, message: str):
        today_key = datetime.now().strftime("%Y-%m-%d")
        if self._last_error_alert_day == today_key:
            return
        self._last_error_alert_day = today_key
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【CHD任务监控】页面请求失败",
            text=message,
        )

    def __persist_config(self):
        self.update_config({
            "enabled": self._enabled,
            "cookie": self._cookie,
            "check_cron": self._check_cron,
            "daily_notify_time": self._daily_notify_time,
            "notify_on_capacity_available": self._notify_on_capacity_available,
            "notify_daily_progress": self._notify_daily_progress,
            "capacity_threshold": self._capacity_threshold,
            "capacity_alert_max_times": self._capacity_alert_max_times,
            "capacity_alert_cooldown_hours": self._capacity_alert_cooldown_hours,
            "reset_capacity_alert_state": self._reset_capacity_alert_state,
            "enable_task_chart": self._enable_task_chart,
            "show_chart_in_dashboard": self._show_chart_in_dashboard,
            "task_type": self._task_type,
            "dashboard_size": self._dashboard_size,
            "dashboard_min_height": self._dashboard_min_height,
            "onlyonce": self._onlyonce,
        })

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        version_flag = getattr(settings, "VERSION_FLAG", "v1")
        cron_field_component = "VCronField" if version_flag == "v2" else "VTextField"
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "enabled", "label": "启用插件"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "onlyonce", "label": "立即运行一次"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "notify_on_capacity_available", "label": "人数不足阈值时通知"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "notify_daily_progress", "label": "每日任务进度通知"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "capacity_alert_max_times",
                                        "label": "名额提醒最多次数",
                                        "type": "number",
                                        "min": 1,
                                        "max": 99,
                                        "placeholder": "3",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "capacity_alert_cooldown_hours",
                                        "label": "名额提醒冷静期(小时)",
                                        "type": "number",
                                        "min": 1,
                                        "max": 168,
                                        "placeholder": "1",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {
                                        "model": "reset_capacity_alert_state",
                                        "label": "重置名额提醒状态",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "enable_task_chart", "label": "任务数据可视化"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSwitch",
                                    "props": {"model": "show_chart_in_dashboard", "label": "在仪表板显示趋势图"},
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "task_type",
                                        "label": "任务类型",
                                        "items": [
                                            {"title": "Master", "value": "Master"},
                                            {"title": "Ultimate", "value": "Ultimate"},
                                            {"title": "Extreme", "value": "Extreme"},
                                            {"title": "Veteran", "value": "Veteran"},
                                            {"title": "Insane", "value": "Insane"}
                                        ]
                                    },
                                }],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": cron_field_component,
                                    "props": {
                                        "model": "check_cron",
                                        "label": "轮询Cron",
                                        "placeholder": "*/30 * * * *",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "daily_notify_time",
                                        "label": "每日通知时间(HH:MM)",
                                        "placeholder": "09:00",
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "capacity_threshold",
                                        "label": "人数阈值",
                                        "type": "number",
                                        "min": 1,
                                        "max": 9999,
                                        "placeholder": "200",
                                    },
                                }],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VSelect",
                                    "props": {
                                        "model": "dashboard_size",
                                        "label": "仪表板组件规格",
                                        "items": [
                                            {"title": "1/3", "value": "one_third"},
                                            {"title": "1/2", "value": "half"},
                                            {"title": "2/3", "value": "two_third"},
                                            {"title": "全宽", "value": "full"}
                                        ]
                                    },
                                }],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [{
                                    "component": "VTextField",
                                    "props": {
                                        "model": "dashboard_min_height",
                                        "label": "组件最小高度（160-520）",
                                        "type": "number",
                                        "min": 160,
                                        "max": 520,
                                        "placeholder": "220",
                                    },
                                }],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VTextarea",
                                    "props": {
                                        "model": "cookie",
                                        "label": "CHD Cookie",
                                        "rows": 4,
                                        "autoGrow": True,
                                        "placeholder": "在浏览器中复制CHDBits登录后的完整Cookie字符串",
                                    },
                                }],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [{
                                    "component": "VAlert",
                                    "props": {
                                        "type": "info",
                                        "variant": "tonal",
                                        "text": "插件会抓取 selfassess.php 页面，解析任务剩余时间、上传下载与做种积分、当前任务人数；通知默认走MoviePilot系统通知通道。",
                                    },
                                }],
                            }
                        ],
                    }
                ],
            }
        ], {
            "enabled": False,
            "cookie": "",
            "check_cron": "*/30 * * * *",
            "daily_notify_time": "09:00",
            "notify_on_capacity_available": True,
            "notify_daily_progress": True,
            "capacity_threshold": 200,
            "capacity_alert_max_times": 3,
            "capacity_alert_cooldown_hours": 1,
            "reset_capacity_alert_state": False,
            "enable_task_chart": False,
            "show_chart_in_dashboard": False,
            "task_type": "Extreme",
            "dashboard_size": "half",
            "dashboard_min_height": 220,
            "onlyonce": False,
        }

    def get_page(self) -> List[dict]:
        latest = dict(self._last_snapshot) if isinstance(self._last_snapshot, dict) else {}

        updated_at = str(latest.get("updated_at") or "未获取")
        countdown = str(latest.get("countdown") or "未解析到")
        upload = str(latest.get("upload") or "未解析到")
        download = str(latest.get("download") or "未解析到")
        seeding = str(latest.get("seeding") or "未解析到")
        has_task = bool(latest.get("has_task"))
        population = latest.get("population")
        population_text = str(population) if isinstance(population, int) else "未解析到"
        task_status = latest.get("task_status") if isinstance(latest.get("task_status"), dict) else {}
        task_type = str(task_status.get("task_type") or self._task_type)
        progress_items = task_status.get("items") if isinstance(task_status.get("items"), list) else []
        chart_data = latest.get("chart") if isinstance(latest.get("chart"), dict) else None

        progress_rows: List[dict] = []
        for item in progress_items:
            label = str(item.get("label") or "")
            text_val = str(item.get("text") or "未解析到")
            progress = max(0.0, min(100.0, float(item.get("progress") or 0) * 100.0))
            done = bool(item.get("done"))
            bar_color = "#43A047" if done else "#9155FD"
            text_color = self.__progress_color(text_val)
            progress_rows.extend([
                {"component": "div", "props": {"style": {"color": text_color, "marginTop": "6px"}}, "text": f"{label}：{text_val}"},
                {
                    "component": "VProgressLinear",
                    "props": {
                        "modelValue": progress,
                        "color": bar_color,
                        "height": 8,
                        "rounded": True,
                        "style": {"marginTop": "4px", "marginBottom": "2px"},
                    },
                },
            ])

        chart_component = self.__build_chart_component(chart_data, height=250)

        return [
            {
                "component": "VCard",
                "props": {"variant": "tonal"},
                "content": [
                    {
                        "component": "VCardText",
                        "content": [
                            {
                                "component": "div",
                                "props": {"class": "text-subtitle-1"},
                                "text": "CHD任务监控 - 当前进度",
                            },
                            {
                                "component": "div",
                                "props": {"class": "text-caption", "style": {"marginTop": "4px", "opacity": 0.8}},
                                "text": f"更新时间：{updated_at}",
                            },
                            {
                                "component": "div",
                                "props": {"style": {"marginTop": "10px", "lineHeight": "1.7", "whiteSpace": "normal"}},
                                "content": [
                                    {"component": "div", "text": f"任务人数：{population_text}"},
                                    {"component": "div", "text": f"任务类型：{task_type}"},
                                    {"component": "div", "text": (f"我的任务：剩余时间 {countdown}" if has_task else "我的任务：当前无任务")},
                                    *(progress_rows if has_task else []),
                                ],
                            },
                            *([
                                {"component": "div", "props": {"style": {"marginTop": "12px"}}, "content": [chart_component]}
                            ] if has_task and self._enable_task_chart and chart_component else []),
                        ],
                    }
                ],
            }
        ]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [
            {"key": "chd_task", "name": "CHD任务监控"},
        ]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        key = key or "chd_task"
        if key != "chd_task":
            return None

        cols = self._SIZE_COLS.get(self._dashboard_size, self._SIZE_COLS["half"])
        attrs = {"title": "CHD任务监控", "refresh": 300, "border": True}

        latest = dict(self._last_snapshot) if isinstance(self._last_snapshot, dict) else {}

        updated_at = str(latest.get("updated_at") or "未获取")
        countdown = str(latest.get("countdown") or "未解析到")
        upload = str(latest.get("upload") or "未解析到")
        download = str(latest.get("download") or "未解析到")
        seeding = str(latest.get("seeding") or "未解析到")
        has_task = bool(latest.get("has_task"))
        population = latest.get("population")
        population_text = str(population) if isinstance(population, int) else "未解析到"
        task_status = latest.get("task_status") if isinstance(latest.get("task_status"), dict) else {}
        task_type = str(task_status.get("task_type") or self._task_type)
        progress_items = task_status.get("items") if isinstance(task_status.get("items"), list) else []
        chart_data = latest.get("chart") if isinstance(latest.get("chart"), dict) else None

        progress_rows: List[dict] = []
        for item in progress_items:
            label = str(item.get("label") or "")
            text_val = str(item.get("text") or "未解析到")
            progress = max(0.0, min(100.0, float(item.get("progress") or 0) * 100.0))
            done = bool(item.get("done"))
            bar_color = "#43A047" if done else "#9155FD"
            text_color = self.__progress_color(text_val)
            progress_rows.extend([
                {"component": "div", "props": {"style": {"color": text_color, "marginTop": "6px"}}, "text": f"{label}：{text_val}"},
                {
                    "component": "VProgressLinear",
                    "props": {
                        "modelValue": progress,
                        "color": bar_color,
                        "height": 8,
                        "rounded": True,
                        "style": {"marginTop": "4px", "marginBottom": "2px"},
                    },
                },
            ])

        chart_component = self.__build_chart_component(chart_data, height=170)

        elements = [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VCard",
                                "props": {"variant": "flat", "style": {"minHeight": f"{self._dashboard_min_height}px"}},
                                "content": [
                                    {
                                        "component": "VCardText",
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "text-caption", "style": {"opacity": 0.8}},
                                                "text": f"更新时间：{updated_at}",
                                            },
                                            {
                                                "component": "div",
                                                "props": {"style": {"marginTop": "10px", "lineHeight": "1.75", "whiteSpace": "normal"}},
                                                "content": [
                                                    {"component": "div", "text": f"任务人数：{population_text}"},
                                                    {"component": "div", "text": f"任务类型：{task_type}"},
                                                    {"component": "div", "text": (f"我的任务：剩余时间 {countdown}" if has_task else "我的任务：当前无任务")},
                                                    *(progress_rows if has_task else []),
                                                ],
                                            },
                                            *([
                                                {"component": "div", "props": {"style": {"marginTop": "12px"}}, "content": [chart_component]}
                                            ] if has_task and self._enable_task_chart and self._show_chart_in_dashboard and chart_component else []),
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ]
        return cols, attrs, elements

    def stop_service(self):
        pass
