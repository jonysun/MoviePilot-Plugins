import math
import re
import threading
from random import shuffle
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from urllib.parse import quote as url_quote
from apscheduler.triggers.cron import CronTrigger

from app.chain.media import MediaChain
from app.chain.recommend import RecommendChain
from app.core.config import settings
from app.core.metainfo import MetaInfo
from app.log import logger
from app.db.models.site import Site
from app.db.models.siteicon import SiteIcon
from app.db.models.sitestatistic import SiteStatistic
from app.db.subscribe_oper import SubscribeOper
from app.db.transferhistory_oper import TransferHistoryOper
from app.plugins import _PluginBase
from app.schemas import MediaType
from app.utils.system import SystemUtils


class DashboardPlus(_PluginBase):
    plugin_name = "仪表板增强"
    plugin_desc = "提供入库热力图、主机性能、站点统计、存储媒体组合四类仪表板组件。"
    plugin_icon = "statistic.png"
    plugin_version = "1.2.10"
    plugin_author = "jonysun"
    author_url = "https://github.com/jonysun"
    plugin_config_prefix = "dashboardplus_"
    plugin_order = 99
    auth_level = 1

    _enabled: bool = True

    # calendar settings
    _show_summary: bool = True
    _show_legend: bool = True
    _show_date_range: bool = False
    _color_theme: str = "mp_purple"
    _show_month_labels: bool = True
    _calendar_align: str = "left"
    _calendar_size: str = "two_third"
    _calendar_auto_stretch: bool = False
    _calendar_stretch_mode: str = "equal"
    _calendar_min_cell_width: int = 8
    _calendar_stretch_row_height: int = 8
    _cell_scale: int = 110
    _cell_gap: int = 2
    _cell_radius: float = 4.0
    _range: str = "1y"
    _label_style: str = "english_abbr"
    _calendar_refresh: int = 300

    # performance settings
    _performance_size: str = "half"
    _performance_height: int = 190
    _performance_refresh: int = 3
    _performance_window: int = 10
    _performance_smooth_window: int = 7
    _performance_cpu_color_preset: str = "purple"
    _performance_memory_color_preset: str = "blue"
    _performance_cpu_color: str = "#9155FD"
    _performance_memory_color: str = "#16B1FF"

    # site statistics settings
    _site_stat_size: str = "full"
    _site_stat_refresh: int = 300
    _site_stat_show_overview: bool = True
    _site_stat_show_logo: bool = True
    _site_stat_only_anomaly: bool = False
    _site_stat_component_max_height: int = 420
    _site_stat_max_height: int = 460

    # storage + media compact settings
    _storage_media_size: str = "half"
    _storage_media_refresh: int = 300
    _storage_media_height: int = 250

    # today recommend settings
    _today_recommend_size: str = "half"
    _today_recommend_count: int = 3
    _today_recommend_speed: int = 5
    _today_recommend_source_scope: str = "all"
    _today_recommend_banner_policy: str = "auto"
    _today_recommend_banner_cache_ttl: int = 43200
    _today_recommend_banner_fill_limit: int = 3
    _today_recommend_image_fit: str = "auto"
    _today_recommend_result_ttl: int = 600
    _today_recommend_min_height: int = 220
    _today_recommend_view_mode: str = "classic"
    _today_recommend_reflective_ratio_left: int = 15
    _today_recommend_reflective_ratio_center: int = 70
    _today_recommend_reflective_ratio_right: int = 15
    _today_recommend_use_prewarm_pool: bool = True
    _today_recommend_prewarm_time: str = "08:00"
    _today_recommend_pool_size: int = 30
    _today_recommend_pool_cache: Dict[str, Any]
    _today_pool_refresh_lock: threading.Lock
    _today_pool_refreshing: bool = False
    _today_pool_last_failed_at: float = 0.0
    _today_pool_failure_backoff: int = 60
    _today_banner_cache: Dict[str, Dict[str, Any]]
    _today_banner_fail_cache: Dict[str, float]
    _today_banner_cache_ops: int = 0
    _today_result_cache: Dict[str, Dict[str, Any]]

    _summary_spacing: int = 8

    _RANGE_DAYS: Dict[str, int] = {
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "1y": 365,
    }

    _SIZE_COLS: Dict[str, Dict[str, int]] = {
        "one_third": {"cols": 12, "md": 4},
        "half": {"cols": 12, "md": 6},
        "two_third": {"cols": 12, "md": 8},
        "full": {"cols": 12},
    }

    _COLOR_THEMES: Dict[str, List[str]] = {
        "github_green": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "high_contrast_green": ["#e5e7eb", "#86efac", "#22c55e", "#16a34a", "#166534"],
        "mp_purple": ["#efebfb", "#d4c4f8", "#b79bf3", "#9c73ee", "#9155FD"],
    }

    _PERFORMANCE_COLOR_PRESETS: Dict[str, str] = {
        "purple": "#9155FD",
        "red": "#EF4444",
        "orange": "#F59E0B",
        "green": "#22C55E",
        "blue": "#16B1FF",
        "cyan": "#06B6D4",
        "indigo": "#6366F1",
        "pink": "#EC4899",
        "teal": "#14B8A6",
        "amber": "#FBBF24",
    }

    def init_plugin(self, config: dict = None):
        config = config or {}
        enabled_value = config.get("enabled")
        if enabled_value is None:
            enabled_value = config.get("enable", True)
        self._enabled = self.__to_bool(enabled_value, default=True)

        self._show_summary = self.__to_bool(config.get("show_summary", True), default=True)
        self._show_legend = self.__to_bool(config.get("show_legend", True), default=True)
        self._show_date_range = self.__to_bool(config.get("show_date_range", False), default=False)

        self._color_theme = config.get("color_theme", "mp_purple")
        if self._color_theme not in self._COLOR_THEMES:
            self._color_theme = "mp_purple"

        self._show_month_labels = self.__to_bool(config.get("show_month_labels", True), default=True)
        self._calendar_align = config.get("calendar_align", "left")
        if self._calendar_align not in {"left", "center", "right"}:
            self._calendar_align = "left"
        self._calendar_auto_stretch = self.__to_bool(config.get("calendar_auto_stretch", False), default=False)
        self._calendar_stretch_mode = str(config.get("calendar_stretch_mode", "equal") or "equal")
        if self._calendar_stretch_mode not in {"equal", "fill"}:
            self._calendar_stretch_mode = "equal"
        self._calendar_min_cell_width = self.__safe_refresh(config.get("calendar_min_cell_width", 8), 6, 24)
        self._calendar_stretch_row_height = self.__safe_refresh(config.get("calendar_stretch_row_height", 8), 0, 40)

        dashboard_size = config.get("dashboard_size", "two_third")
        self._calendar_size = config.get("calendar_size", dashboard_size)
        if self._calendar_size not in self._SIZE_COLS:
            self._calendar_size = "two_third"

        self._performance_size = config.get("performance_size", "half")
        if self._performance_size not in self._SIZE_COLS:
            self._performance_size = "half"

        self._site_stat_size = config.get("site_stat_size", "full")
        if self._site_stat_size not in self._SIZE_COLS:
            self._site_stat_size = "full"

        self._storage_media_size = config.get("storage_media_size", "half")
        if self._storage_media_size not in self._SIZE_COLS:
            self._storage_media_size = "half"

        self._today_recommend_size = config.get("today_recommend_size", "half")
        if self._today_recommend_size not in self._SIZE_COLS:
            self._today_recommend_size = "half"
        self._today_recommend_count = self.__safe_refresh(config.get("today_recommend_count", 3), 1, 5)
        self._today_recommend_speed = self.__safe_refresh(config.get("today_recommend_speed", 5), 3, 10)
        self._today_recommend_source_scope = str(config.get("today_recommend_source_scope", "all") or "all")
        if self._today_recommend_source_scope not in {"all", "douban", "imdb"}:
            self._today_recommend_source_scope = "all"
        self._today_recommend_banner_policy = str(config.get("today_recommend_banner_policy", "auto") or "auto")
        if self._today_recommend_banner_policy not in {"auto", "existing_only", "enhanced"}:
            self._today_recommend_banner_policy = "auto"
        self._today_recommend_banner_cache_ttl = self.__safe_refresh(
            config.get("today_recommend_banner_cache_ttl", 43200),
            600,
            172800
        )
        self._today_recommend_banner_fill_limit = self.__safe_refresh(
            config.get("today_recommend_banner_fill_limit", 3),
            1,
            10
        )
        self._today_recommend_result_ttl = self.__safe_refresh(
            config.get("today_recommend_result_ttl", 600),
            30,
            1800
        )
        self._today_recommend_min_height = self.__safe_refresh(
            config.get("today_recommend_min_height", 220),
            160,
            480
        )
        self._today_recommend_view_mode = str(config.get("today_recommend_view_mode", "classic") or "classic")
        if self._today_recommend_view_mode not in {"classic", "reflective"}:
            self._today_recommend_view_mode = "classic"
        reflective_ratio_left = self.__safe_refresh(config.get("today_recommend_reflective_ratio_left", 15), 5, 90)
        reflective_ratio_center = self.__safe_refresh(config.get("today_recommend_reflective_ratio_center", 70), 5, 90)
        reflective_ratio_right = self.__safe_refresh(config.get("today_recommend_reflective_ratio_right", 15), 5, 90)
        (
            self._today_recommend_reflective_ratio_left,
            self._today_recommend_reflective_ratio_center,
            self._today_recommend_reflective_ratio_right,
        ) = self.__normalize_reflective_ratios(
            reflective_ratio_left,
            reflective_ratio_center,
            reflective_ratio_right,
        )
        self._today_recommend_image_fit = str(config.get("today_recommend_image_fit", "auto") or "auto")
        if self._today_recommend_image_fit not in {"auto", "cover", "contain", "fill"}:
            self._today_recommend_image_fit = "auto"
        self._today_recommend_use_prewarm_pool = self.__to_bool(
            config.get("today_recommend_use_prewarm_pool", True),
            default=True
        )
        raw_prewarm_time = str(config.get("today_recommend_prewarm_time", "08:00") or "08:00").strip()
        self._today_recommend_prewarm_time = self.__normalize_hhmm(raw_prewarm_time)
        self._today_recommend_pool_size = self.__safe_refresh(
            config.get("today_recommend_pool_size", 30),
            10,
            200
        )
        if not isinstance(getattr(self, "_today_banner_cache", None), dict):
            self._today_banner_cache = {}
        if not isinstance(getattr(self, "_today_banner_fail_cache", None), dict):
            self._today_banner_fail_cache = {}
        if not isinstance(getattr(self, "_today_banner_cache_ops", None), int):
            self._today_banner_cache_ops = 0
        if not isinstance(getattr(self, "_today_result_cache", None), dict):
            self._today_result_cache = {}
        if not isinstance(getattr(self, "_today_recommend_pool_cache", None), dict):
            self._today_recommend_pool_cache = {}
        lock_obj = getattr(self, "_today_pool_refresh_lock", None)
        if lock_obj is None or not hasattr(lock_obj, "acquire"):
            self._today_pool_refresh_lock = threading.Lock()
        if not isinstance(getattr(self, "_today_pool_refreshing", None), bool):
            self._today_pool_refreshing = False
        if not isinstance(getattr(self, "_today_pool_last_failed_at", None), (int, float)):
            self._today_pool_last_failed_at = 0.0

        self._cell_scale = self.__safe_scale(config.get("cell_scale", 110))
        self._cell_gap = self.__safe_refresh(config.get("cell_gap", 2), 0, 8)
        self._cell_radius = self.__safe_radius(config.get("cell_radius", 4.0))

        self._range = config.get("range", "1y")
        if self._range not in self._RANGE_DAYS:
            self._range = "1y"

        self._label_style = config.get("label_style", "english_abbr")
        if self._label_style not in {"english_abbr", "chinese", "numeric"}:
            self._label_style = "english_abbr"

        self._calendar_refresh = self.__safe_refresh(config.get("calendar_refresh", 300), 1, 3600)

        self._performance_height = self.__safe_refresh(config.get("performance_height", 190), 120, 320)
        self._performance_refresh = self.__safe_refresh(config.get("performance_refresh", 3), 1, 60)
        self._performance_window = self.__safe_refresh(config.get("performance_window", 10), 1, 60)
        self._performance_smooth_window = self.__safe_refresh(config.get("performance_smooth_window", 7), 1, 15)
        self._performance_cpu_color_preset = str(config.get("performance_cpu_color_preset", "purple") or "purple")
        self._performance_memory_color_preset = str(config.get("performance_memory_color_preset", "blue") or "blue")
        if self._performance_cpu_color_preset not in self._PERFORMANCE_COLOR_PRESETS:
            self._performance_cpu_color_preset = "purple"
        if self._performance_memory_color_preset not in self._PERFORMANCE_COLOR_PRESETS:
            self._performance_memory_color_preset = "blue"

        cpu_color_legacy = config.get("performance_cpu_color")
        mem_color_legacy = config.get("performance_memory_color")
        self._performance_cpu_color = self.__resolve_performance_color(self._performance_cpu_color_preset,
                                                                       cpu_color_legacy,
                                                                       "#9155FD")
        self._performance_memory_color = self.__resolve_performance_color(self._performance_memory_color_preset,
                                                                          mem_color_legacy,
                                                                          "#16B1FF")

        self._site_stat_refresh = self.__safe_refresh(config.get("site_stat_refresh", 300), 10, 3600)
        self._site_stat_show_overview = self.__to_bool(config.get("site_stat_show_overview", True), default=True)
        self._site_stat_show_logo = self.__to_bool(config.get("site_stat_show_logo", True), default=True)
        self._site_stat_only_anomaly = self.__to_bool(config.get("site_stat_only_anomaly", False), default=False)
        self._site_stat_component_max_height = self.__safe_refresh(
            config.get("site_stat_component_max_height", 420),
            240,
            1200
        )
        self._site_stat_max_height = self.__safe_refresh(config.get("site_stat_max_height", 460), 300, 900)

        self._storage_media_refresh = self.__safe_refresh(config.get("storage_media_refresh", 300), 10, 3600)
        self._storage_media_height = self.__safe_refresh(config.get("storage_media_height", 250), 180, 420)
        summary_spacing_raw = config.get("calendar_stretch_row_height", config.get("summary_spacing", 8))
        self._summary_spacing = self.__safe_refresh(summary_spacing_raw, 0, 40)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        # 热力图与主机性能复用现有配置结构，再补充 C/D 组件配置
        form_content = [
            {
                "component": "VRow",
                "props": {"style": {"marginTop": "0px"}},
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [{"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}]
                    }
                ]
            },
            {
                "component": "VExpansionPanels",
                "props": {"variant": "accordion", "multiple": True},
                "content": [
                    {
                        "component": "VExpansionPanel",
                        "content": [
                            {"component": "VExpansionPanelTitle", "text": "热力图设置"},
                            {
                                "component": "VExpansionPanelText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "range",
                                                        "label": "统计区间",
                                                        "items": [
                                                            {"title": "1个月", "value": "1m"},
                                                            {"title": "3个月", "value": "3m"},
                                                            {"title": "6个月", "value": "6m"},
                                                            {"title": "1年", "value": "1y"}
                                                        ]
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "color_theme",
                                                        "label": "颜色主题",
                                                        "items": [
                                                            {"title": "GitHub Green", "value": "github_green"},
                                                            {"title": "High Contrast Green", "value": "high_contrast_green"},
                                                            {"title": "MoviePilot Purple", "value": "mp_purple"}
                                                        ]
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "calendar_size",
                                                        "label": "热力组件宽度",
                                                        "items": [
                                                            {"title": "1/3（33%）", "value": "one_third"},
                                                            {"title": "1/2（50%）", "value": "half"},
                                                            {"title": "2/3（66%）", "value": "two_third"},
                                                            {"title": "全宽（100%）", "value": "full"}
                                                        ]
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "calendar_refresh",
                                                        "label": "热力自动刷新（秒）",
                                                        "type": "number",
                                                        "min": 1,
                                                        "max": 3600,
                                                        "placeholder": "300"
                                                    }
                                                }]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "cell_scale",
                                                        "label": "格子尺寸缩放（70-150%）",
                                                        "type": "number",
                                                        "min": 70,
                                                        "max": 150,
                                                        "placeholder": "110",
                                                        "disabled": self._calendar_auto_stretch
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "cell_radius",
                                                        "label": "格子圆角（0-8）",
                                                        "type": "number",
                                                        "min": 0,
                                                        "max": 8,
                                                        "step": 0.5,
                                                        "placeholder": "4"
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "cell_gap",
                                                        "label": "格子间隔（0-8）",
                                                        "type": "number",
                                                        "min": 0,
                                                        "max": 8,
                                                        "placeholder": "2"
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "label_style",
                                                        "label": "月/星期标注样式",
                                                        "items": [
                                                            {"title": "英文简称", "value": "english_abbr"},
                                                            {"title": "中文", "value": "chinese"},
                                                            {"title": "数字", "value": "numeric"}
                                                        ]
                                                    }
                                                }]
                                            },
                                             {
                                                 "component": "VCol",
                                                 "props": {"cols": 12, "md": 3},
                                                 "content": [{
                                                     "component": "VSelect",
                                                     "props": {
                                                         "model": "calendar_align",
                                                         "label": "热力本体对齐",
                                                         "items": [
                                                             {"title": "靠左（默认）", "value": "left"},
                                                             {"title": "居中", "value": "center"},
                                                             {"title": "靠右", "value": "right"}
                                                         ]
                                                     }
                                                 }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3, "style": {"display": "block" if self._calendar_auto_stretch else "none"}},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "calendar_min_cell_width",
                                                        "label": "自动拉伸最小格宽（6-24）",
                                                        "type": "number",
                                                        "min": 6,
                                                        "max": 24,
                                                        "placeholder": "8"
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3, "style": {"display": "block" if self._calendar_auto_stretch else "none"}},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "calendar_stretch_mode",
                                                        "label": "拉伸模式",
                                                        "items": [
                                                            {"title": "等比方格（推荐）", "value": "equal"},
                                                            {"title": "完全填充", "value": "fill"}
                                                        ]
                                                    }
                                                }]
                                            },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3, "style": {"display": "block" if self._calendar_auto_stretch else "none"}},
                                                "content": [{
                                                    "component": "VTextField",
                                                    "props": {
                                                        "model": "calendar_stretch_row_height",
                                                        "label": "统计信息段前行高（0-40）",
                                                        "type": "number",
                                                        "min": 0,
                                                        "max": 40,
                                                        "placeholder": "8"
                                                    }
                                                }]
                                            }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                             {
                                                 "component": "VCol",
                                                 "props": {"cols": 12, "md": 3},
                                                 "content": [{
                                                     "component": "VSwitch",
                                                     "props": {"model": "calendar_auto_stretch", "label": "自动拉伸填充"}
                                                 }]
                                             },
                                             {
                                                 "component": "VCol",
                                                 "props": {"cols": 12, "md": 3},
                                                 "content": [{
                                                     "component": "VSwitch",
                                                     "props": {"model": "show_month_labels", "label": "显示月份标签"}
                                                 }]
                                             },
                                             {
                                                 "component": "VCol",
                                                 "props": {"cols": 12, "md": 3},
                                                 "content": [{
                                                     "component": "VSwitch",
                                                     "props": {"model": "show_legend", "label": "显示少到多图例"}
                                                 }]
                                             },
                                             {
                                                 "component": "VCol",
                                                 "props": {"cols": 12, "md": 3},
                                                 "content": [{
                                                     "component": "VSwitch",
                                                     "props": {"model": "show_date_range", "label": "显示统计区间"}
                                                 }]
                                             },
                                              {
                                                  "component": "VCol",
                                                  "props": {"cols": 12, "md": 3},
                                                  "content": [{
                                                      "component": "VSwitch",
                                                      "props": {"model": "show_summary", "label": "显示摘要信息"}
                                                  }]
                                              }
                                        ]
                                    },
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12},
                                                "content": [{
                                                    "component": "VAlert",
                                                    "props": {"type": "info", "variant": "tonal", "density": "compact"},
                                                    "text": "“显示摘要信息”用于控制热力图下方统计行（总入库量/活跃天数/峰值单日）显示与否。"
                                                }]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VExpansionPanel",
                        "content": [
                            {"component": "VExpansionPanelTitle", "text": "主机性能设置"},
                            {
                                "component": "VExpansionPanelText",
                                "content": [
                                    {
                                        "component": "VRow",
                                        "content": [
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VSelect", "props": {"model": "performance_size", "label": "性能组件宽度", "items": [{"title": "1/3（33%）", "value": "one_third"}, {"title": "1/2（50%）", "value": "half"}, {"title": "2/3（66%）", "value": "two_third"}, {"title": "全宽（100%）", "value": "full"}]}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "performance_height", "label": "性能图高度（120-320）", "type": "number", "min": 120, "max": 320, "placeholder": "190"}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "performance_refresh", "label": "性能图刷新间隔（秒）", "type": "number", "min": 1, "max": 60, "placeholder": "3"}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "performance_window", "label": "折线窗口（分钟1-60）", "type": "number", "min": 1, "max": 60, "placeholder": "10"}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VSelect", "props": {"model": "performance_cpu_color_preset", "label": "CPU折线颜色", "items": [{"title": "紫色", "value": "purple"}, {"title": "红色", "value": "red"}, {"title": "橙色", "value": "orange"}, {"title": "绿色", "value": "green"}, {"title": "蓝色", "value": "blue"}, {"title": "青色", "value": "cyan"}, {"title": "靛蓝", "value": "indigo"}, {"title": "粉色", "value": "pink"}, {"title": "青绿", "value": "teal"}, {"title": "琥珀", "value": "amber"}]}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VSelect", "props": {"model": "performance_memory_color_preset", "label": "内存折线颜色", "items": [{"title": "蓝色", "value": "blue"}, {"title": "紫色", "value": "purple"}, {"title": "红色", "value": "red"}, {"title": "橙色", "value": "orange"}, {"title": "绿色", "value": "green"}, {"title": "青色", "value": "cyan"}, {"title": "靛蓝", "value": "indigo"}, {"title": "粉色", "value": "pink"}, {"title": "青绿", "value": "teal"}, {"title": "琥珀", "value": "amber"}]}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "performance_smooth_window", "label": "折线平滑度（1-15）", "type": "number", "min": 1, "max": 15, "placeholder": "7"}}]}
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VExpansionPanel",
                        "content": [
                            {"component": "VExpansionPanelTitle", "text": "站点统计设置"},
                            {
                                "component": "VExpansionPanelText",
                                "content": [{
                                    "component": "VRow",
                                    "content": [
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSelect", "props": {"model": "site_stat_size", "label": "组件宽度", "items": [{"title": "1/3（33%）", "value": "one_third"}, {"title": "1/2（50%）", "value": "half"}, {"title": "2/3（66%）", "value": "two_third"}, {"title": "全宽（100%）", "value": "full"}]}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VTextField", "props": {"model": "site_stat_refresh", "label": "刷新间隔（秒）", "type": "number", "min": 10, "max": 3600, "placeholder": "300"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VTextField", "props": {"model": "site_stat_component_max_height", "label": "组件自身最大高度", "type": "number", "min": 240, "max": 1200, "placeholder": "420"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VTextField", "props": {"model": "site_stat_max_height", "label": "组件内可视高度", "type": "number", "min": 300, "max": 900, "placeholder": "460"}}]}
                                    ]
                                }, {
                                    "component": "VRow",
                                    "content": [
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSwitch", "props": {"model": "site_stat_show_overview", "label": "显示统计概览"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSwitch", "props": {"model": "site_stat_show_logo", "label": "显示站点Logo"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSwitch", "props": {"model": "site_stat_only_anomaly", "label": "仅显示异常站点"}}]}
                                    ]
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VExpansionPanel",
                        "content": [
                            {"component": "VExpansionPanelTitle", "text": "储存情况与媒体统计设置"},
                            {
                                "component": "VExpansionPanelText",
                                "content": [{
                                    "component": "VRow",
                                    "content": [
                                        {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [{"component": "VSelect", "props": {"model": "storage_media_size", "label": "组件宽度", "items": [{"title": "1/3（33%）", "value": "one_third"}, {"title": "1/2（50%）", "value": "half"}, {"title": "2/3（66%）", "value": "two_third"}, {"title": "全宽（100%）", "value": "full"}]}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "storage_media_refresh", "label": "刷新间隔（秒）", "type": "number", "min": 10, "max": 3600, "placeholder": "300"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VTextField", "props": {"model": "storage_media_height", "label": "组件高度（180-420）", "type": "number", "min": 180, "max": 420, "placeholder": "250"}}]}
                                    ]
                                }]
                            }
                        ]
                    },
                    {
                        "component": "VExpansionPanel",
                        "content": [
                            {"component": "VExpansionPanelTitle", "text": "今日推荐设置"},
                            {
                                "component": "VExpansionPanelText",
                                "content": [{
                                    "component": "VRow",
                                    "content": [
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VSelect",
                                                "props": {
                                                    "model": "today_recommend_size",
                                                    "label": "组件宽度",
                                                    "items": [
                                                        {"title": "1/3（33%）", "value": "one_third"},
                                                        {"title": "1/2（50%）", "value": "half"},
                                                        {"title": "2/3（66%）", "value": "two_third"},
                                                        {"title": "3/3（100%）", "value": "full"}
                                                    ]
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_count",
                                                    "label": "轮播数量（1-5）",
                                                    "type": "number",
                                                    "min": 1,
                                                    "max": 5,
                                                    "placeholder": "3"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_speed",
                                                    "label": "轮播速度（3-10秒）",
                                                    "type": "number",
                                                    "min": 3,
                                                    "max": 10,
                                                    "placeholder": "5"
                                                }
                                            }]
                                        }
                                    ]
                                 }, {
                                     "component": "VRow",
                                     "content": [
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VSelect",
                                                "props": {
                                                    "model": "today_recommend_view_mode",
                                                    "label": "展示模式",
                                                    "items": [
                                                        {"title": "经典轮播", "value": "classic"},
                                                        {"title": "反射视角", "value": "reflective"}
                                                    ]
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_reflective_ratio_left",
                                                    "label": "左侧比例（%）",
                                                    "type": "number",
                                                    "min": 5,
                                                    "max": 90,
                                                    "placeholder": "15"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_reflective_ratio_center",
                                                    "label": "中间比例（%）",
                                                    "type": "number",
                                                    "min": 5,
                                                    "max": 90,
                                                    "placeholder": "70"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_reflective_ratio_right",
                                                    "label": "右侧比例（%）",
                                                    "type": "number",
                                                    "min": 5,
                                                    "max": 90,
                                                    "placeholder": "15"
                                                }
                                            }]
                                        }
                                    ]
                                }, {
                                    "component": "VRow",
                                    "content": [
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VSwitch",
                                                "props": {
                                                    "model": "today_recommend_use_prewarm_pool",
                                                    "label": "启用预热池"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_prewarm_time",
                                                    "label": "预热时间（HH:MM）",
                                                    "placeholder": "08:00"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 4},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_pool_size",
                                                    "label": "预热池总数（10-200）",
                                                    "type": "number",
                                                    "min": 10,
                                                    "max": 200,
                                                    "placeholder": "30"
                                                }
                                            }]
                                        }
                                    ]
                                }, {
                                    "component": "VRow",
                                    "content": [
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VSelect",
                                                "props": {
                                                    "model": "today_recommend_source_scope",
                                                    "label": "推荐来源",
                                                    "items": [
                                                        {"title": "全部", "value": "all"},
                                                        {"title": "豆瓣", "value": "douban"},
                                                        {"title": "IMDb", "value": "imdb"}
                                                    ]
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VSelect",
                                                "props": {
                                                    "model": "today_recommend_banner_policy",
                                                    "label": "横幅来源策略",
                                                    "items": [
                                                        {"title": "自动（推荐）", "value": "auto"},
                                                        {"title": "仅现有来源", "value": "existing_only"},
                                                        {"title": "增强补全", "value": "enhanced"}
                                                    ]
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_banner_cache_ttl",
                                                    "label": "横幅缓存TTL（秒）",
                                                    "type": "number",
                                                    "min": 600,
                                                    "max": 172800,
                                                    "placeholder": "43200"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_banner_fill_limit",
                                                    "label": "每轮补图上限（1-10）",
                                                    "type": "number",
                                                    "min": 1,
                                                    "max": 10,
                                                    "placeholder": "3"
                                                }
                                            }]
                                        },
                                            {
                                                "component": "VCol",
                                                "props": {"cols": 12, "md": 3},
                                                "content": [{
                                                    "component": "VSelect",
                                                    "props": {
                                                        "model": "today_recommend_image_fit",
                                                        "label": "图片适配模式",
                                                        "items": [
                                                            {"title": "自动拉伸铺满（不裁切）", "value": "auto"},
                                                            {"title": "自动裁切铺满（cover）", "value": "cover"},
                                                            {"title": "完整显示（不放大）", "value": "contain"},
                                                            {"title": "强制拉伸（可能变形）", "value": "fill"}
                                                        ]
                                                    }
                                                }]
                                            },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_result_ttl",
                                                    "label": "结果缓存TTL（秒）",
                                                    "type": "number",
                                                    "min": 30,
                                                    "max": 1800,
                                                    "placeholder": "600"
                                                }
                                            }]
                                        },
                                        {
                                            "component": "VCol",
                                            "props": {"cols": 12, "md": 3},
                                            "content": [{
                                                "component": "VTextField",
                                                "props": {
                                                    "model": "today_recommend_min_height",
                                                    "label": "组件最低高度（160-480）",
                                                    "type": "number",
                                                    "min": 160,
                                                    "max": 480,
                                                    "placeholder": "220"
                                                }
                                            }]
                                        }
                                    ]
                                }]
                            }
                        ]
                    }
                ]
            }
        ]

        return [{
            "component": "VForm",
            "content": form_content,
        }], {
            "enabled": self._enabled,
            "show_summary": self._show_summary,
            "show_legend": self._show_legend,
            "show_date_range": self._show_date_range,
            "color_theme": self._color_theme,
            "show_month_labels": self._show_month_labels,
            "calendar_align": self._calendar_align,
            "calendar_auto_stretch": self._calendar_auto_stretch,
            "calendar_stretch_mode": self._calendar_stretch_mode,
            "calendar_min_cell_width": self._calendar_min_cell_width,
            "calendar_stretch_row_height": self._calendar_stretch_row_height,
            "dashboard_size": self._calendar_size,
            "calendar_size": self._calendar_size,
            "performance_size": self._performance_size,
            "site_stat_size": self._site_stat_size,
            "storage_media_size": self._storage_media_size,
            "today_recommend_size": self._today_recommend_size,
            "today_recommend_count": self._today_recommend_count,
            "today_recommend_speed": self._today_recommend_speed,
            "today_recommend_use_prewarm_pool": self._today_recommend_use_prewarm_pool,
            "today_recommend_prewarm_time": self._today_recommend_prewarm_time,
            "today_recommend_pool_size": self._today_recommend_pool_size,
            "today_recommend_source_scope": self._today_recommend_source_scope,
            "today_recommend_banner_policy": self._today_recommend_banner_policy,
            "today_recommend_banner_cache_ttl": self._today_recommend_banner_cache_ttl,
            "today_recommend_banner_fill_limit": self._today_recommend_banner_fill_limit,
            "today_recommend_image_fit": self._today_recommend_image_fit,
            "today_recommend_result_ttl": self._today_recommend_result_ttl,
            "today_recommend_min_height": self._today_recommend_min_height,
            "today_recommend_view_mode": self._today_recommend_view_mode,
            "today_recommend_reflective_ratio_left": self._today_recommend_reflective_ratio_left,
            "today_recommend_reflective_ratio_center": self._today_recommend_reflective_ratio_center,
            "today_recommend_reflective_ratio_right": self._today_recommend_reflective_ratio_right,
            "cell_scale": self._cell_scale,
            "cell_gap": self._cell_gap,
            "cell_radius": self._cell_radius,
            "range": self._range,
            "label_style": self._label_style,
            "calendar_refresh": self._calendar_refresh,
            "performance_height": self._performance_height,
            "performance_refresh": self._performance_refresh,
            "performance_window": self._performance_window,
            "performance_smooth_window": self._performance_smooth_window,
            "performance_cpu_color_preset": self._performance_cpu_color_preset,
            "performance_memory_color_preset": self._performance_memory_color_preset,
            "site_stat_refresh": self._site_stat_refresh,
            "site_stat_show_overview": self._site_stat_show_overview,
            "site_stat_show_logo": self._site_stat_show_logo,
            "site_stat_only_anomaly": self._site_stat_only_anomaly,
            "site_stat_component_max_height": self._site_stat_component_max_height,
            "site_stat_max_height": self._site_stat_max_height,
            "storage_media_refresh": self._storage_media_refresh,
            "storage_media_height": self._storage_media_height,
        }

    def get_page(self) -> List[dict]:
        return [{
            "component": "div",
            "props": {"class": "text-center"},
            "text": "请在仪表板中添加“媒体入库热力图 / 主机性能 / 站点统计 / 储存情况与媒体统计”组件查看。"
        }]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [
            {"key": "calendar", "name": "媒体入库热力图"},
            {"key": "performance", "name": "主机性能"},
            {"key": "site_statistics", "name": "站点统计"},
            {"key": "storage_media_compact", "name": "储存情况与媒体统计"},
            {"key": "today_recommend", "name": "今日推荐"},
        ]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        if key and key not in {"calendar", "performance", "site_statistics", "storage_media_compact", "today_recommend"}:
            return None

        key = key or "calendar"
        cols = {"cols": 12}
        attrs = {"refresh": self._calendar_refresh, "title": "媒体入库热力图", "border": True}

        try:
            if key == "performance":
                cols = self._SIZE_COLS.get(self._performance_size, self._SIZE_COLS["half"])
                attrs = {"refresh": self._performance_refresh, "title": "主机性能", "border": True}
                perf_data = self.__load_performance_data()
                perf_series = self.__update_performance_series(perf_data, self._performance_window, self._performance_refresh)
                elements = self.__build_performance_elements(perf_data, perf_series)
            elif key == "site_statistics":
                cols = self._SIZE_COLS.get(self._site_stat_size, self._SIZE_COLS["full"])
                attrs = {"refresh": self._site_stat_refresh, "title": "站点统计", "border": True}
                elements = self.__build_site_statistics_elements()
            elif key == "storage_media_compact":
                cols = self._SIZE_COLS.get(self._storage_media_size, self._SIZE_COLS["half"])
                attrs = {"refresh": self._storage_media_refresh, "title": "储存情况与媒体统计", "border": True}
                elements = self.__build_storage_media_compact_elements()
            elif key == "today_recommend":
                cols = self._SIZE_COLS.get(self._today_recommend_size, self._SIZE_COLS["half"])
                attrs = {"refresh": 300, "title": "今日推荐", "border": True}
                elements = self.__build_today_recommend_elements()
            else:
                cols = self._SIZE_COLS.get(self._calendar_size, self._SIZE_COLS["two_third"])
                attrs = {"refresh": self._calendar_refresh, "title": "媒体入库热力图", "border": True}
                days = self._RANGE_DAYS.get(self._range, 365)
                grid_data = self.__build_calendar_grid(days=days)
                elements = self.__build_calendar_elements(grid_data)
            return cols, attrs, elements
        except Exception as err:
            return cols, attrs, [{
                "component": "VAlert",
                "props": {"type": "warning", "variant": "tonal", "density": "compact"},
                "text": f"仪表板组件数据加载失败：{str(err)}",
            }]

    def stop_service(self):
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        if not self._enabled or not self._today_recommend_use_prewarm_pool:
            return []
        try:
            hour_text, minute_text = self._today_recommend_prewarm_time.split(":", 1)
            hour = int(hour_text)
            minute = int(minute_text)
        except Exception:
            hour = 8
            minute = 0
        return [{
            "id": "DashboardPlusTodayRecommendPrewarm",
            "name": "今日推荐预热池刷新服务",
            "trigger": CronTrigger(hour=hour, minute=minute),
            "func": self.__scheduled_prewarm_today_pool,
            "kwargs": {},
        }]

    def __scheduled_prewarm_today_pool(self):
        try:
            self.__refresh_today_pool_if_needed(force=True)
        except Exception as err:
            logger.warning("[dashboardplus:today_recommend] scheduled prewarm failed: %s", str(err))

    @staticmethod
    def __safe_refresh(raw_value: Any, min_value: int, max_value: int) -> int:
        try:
            value = int(raw_value)
            if value < min_value:
                return min_value
            if value > max_value:
                return max_value
            return value
        except Exception:
            return min_value

    @staticmethod
    def __safe_scale(raw_value: Any) -> int:
        return DashboardPlus.__safe_refresh(raw_value, 70, 150)

    @staticmethod
    def __safe_radius(raw_value: Any) -> float:
        try:
            value = float(raw_value)
            if value < 0:
                return 0.0
            if value > 8:
                return 8.0
            return value
        except Exception:
            return 4.0

    @staticmethod
    def __safe_color(raw_value: Any, default: str) -> str:
        value = str(raw_value or "").strip()
        if len(value) == 7 and value.startswith("#"):
            hex_part = value[1:]
            if all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
                return value
        return default

    def __resolve_performance_color(self, preset: str, legacy_value: Any, default: str) -> str:
        if preset in self._PERFORMANCE_COLOR_PRESETS:
            return self._PERFORMANCE_COLOR_PRESETS[preset]
        return self.__safe_color(legacy_value, default)

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
    def __normalize_hhmm(value: str) -> str:
        raw = str(value or "").strip()
        matched = re.match(r"^(\d{1,2}):(\d{1,2})$", raw)
        if not matched:
            return "08:00"
        hours = int(matched.group(1))
        minutes = int(matched.group(2))
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return "08:00"
        return f"{hours:02d}:{minutes:02d}"

    @staticmethod
    def __normalize_reflective_ratios(left: int, center: int, right: int) -> Tuple[int, int, int]:
        if left + center + right == 100:
            return left, center, right
        return 15, 70, 15

    def __build_calendar_grid(self, days: int) -> Dict[str, Any]:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        count_by_day = self.__load_daily_counts(days=days)

        leading_blanks = start_date.weekday()
        total_cells = leading_blanks + days
        trailing_blanks = (7 - (total_cells % 7)) % 7
        total_cells += trailing_blanks
        total_weeks = total_cells // 7

        max_count = max(count_by_day.values()) if count_by_day else 0
        month_labels: Dict[int, str] = {}
        weeks: List[List[Dict[str, Any]]] = []

        for week_index in range(total_weeks):
            week_cells: List[Dict[str, Any]] = []
            for weekday in range(7):
                flat_index = week_index * 7 + weekday
                offset = flat_index - leading_blanks

                if 0 <= offset < days:
                    current_day = start_date + timedelta(days=offset)
                    day_key = current_day.isoformat()
                    day_count = count_by_day.get(day_key, 0)
                    level = self.__count_to_level(day_count, max_count)
                    cell = {"date": day_key, "count": day_count, "level": level, "in_range": True,
                            "tooltip": f"{day_key}: {day_count}"}
                    if self._show_month_labels and current_day.day == 1 and week_index not in month_labels:
                        month_labels[week_index] = self.__month_label(current_day.month)
                else:
                    cell = {"date": None, "count": 0, "level": 0, "in_range": False, "tooltip": ""}
                week_cells.append(cell)
            weeks.append(week_cells)

        total_count = sum(count_by_day.values()) if count_by_day else 0
        active_days = sum(1 for value in count_by_day.values() if value > 0)

        return {
            "weeks": weeks,
            "week_count": total_weeks,
            "month_labels": month_labels,
            "max_count": max_count,
            "total_count": total_count,
            "active_days": active_days,
            "date_range": f"{start_date.isoformat()} ~ {end_date.isoformat()}",
        }

    @staticmethod
    def __count_to_level(count: int, max_count: int) -> int:
        if count <= 0 or max_count <= 0:
            return 0
        return max(1, min(4, math.ceil((count / max_count) * 4)))

    @staticmethod
    def __load_daily_counts(days: int) -> Dict[str, int]:
        today = date.today()
        first_day = today - timedelta(days=days - 1)
        result = {(first_day + timedelta(days=delta)).isoformat(): 0 for delta in range(days)}
        rows = TransferHistoryOper().statistic(days=days)
        for item in rows:
            if not item or len(item) < 2:
                continue
            day_key = str(item[0])
            if day_key in result:
                result[day_key] = int(item[1])
        return result

    @staticmethod
    def __load_performance_data() -> Dict[str, Any]:
        try:
            cpu = SystemUtils.cpu_usage()
            memory = SystemUtils.memory_usage()
            memory_usage = int(memory[1]) if memory and len(memory) > 1 else 0
        except Exception:
            cpu = 0
            memory_usage = 0

        if not isinstance(cpu, (int, float)) or not math.isfinite(float(cpu)):
            cpu = 0
        if not isinstance(memory_usage, (int, float)):
            memory_usage = 0

        cpu = max(0.0, min(100.0, float(cpu)))
        memory_percent = max(0, min(100, int(memory_usage)))
        memory_mb = 0
        try:
            memory_mb = int(round(memory[0] / 1024 / 1024)) if memory and len(memory) > 0 else 0
        except Exception:
            memory_mb = 0
        memory_mb = max(0, memory_mb)
        return {"cpu": round(cpu, 1), "memory_percent": memory_percent, "memory_mb": memory_mb}

    def __update_performance_series(self, perf_data: Dict[str, Any], window_minutes: int, sample_seconds: int) -> Dict[str, List[Any]]:
        key = "performance_series"
        raw = self.get_data(key) or []
        now = datetime.now()
        cutoff = now - timedelta(minutes=window_minutes)

        normalized = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            ts_text = item.get("ts")
            cpu_val = item.get("cpu")
            mem_val = item.get("memory_mb")
            try:
                ts = datetime.fromisoformat(str(ts_text))
                if ts.tzinfo is not None:
                    ts = ts.astimezone().replace(tzinfo=None)
                cpu_num = float(cpu_val)
                mem_num = float(mem_val)
            except Exception:
                continue
            if ts >= cutoff:
                normalized.append({"ts": ts.isoformat(), "cpu": max(0.0, min(100.0, cpu_num)),
                                   "memory_mb": max(0.0, mem_num)})

        normalized.append({"ts": now.isoformat(), "cpu": perf_data["cpu"], "memory_mb": perf_data["memory_mb"]})

        points_by_window = int((window_minutes * 60) / max(1, sample_seconds)) + 2
        max_points = max(60, points_by_window)
        if len(normalized) > max_points:
            normalized = normalized[-max_points:]

        self.save_data(key, normalized)

        categories, cpu_series, memory_series = [], [], []
        for item in normalized:
            ts = datetime.fromisoformat(item["ts"])
            categories.append(ts.strftime("%H:%M:%S"))
            cpu_series.append(round(float(item["cpu"]), 1))
            memory_series.append(round(float(item["memory_mb"]), 1))

        return {"categories": categories, "cpu": cpu_series, "memory": memory_series}

    def __month_label(self, month: int) -> str:
        if self._label_style == "chinese":
            return f"{month}月"
        if self._label_style == "numeric":
            return str(month)
        month_abbr = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return month_abbr[month - 1]

    def __weekday_labels(self) -> List[str]:
        if self._label_style == "chinese":
            return ["周一", "", "周三", "", "周五", "", "周日"]
        if self._label_style == "numeric":
            return ["1", "", "3", "", "5", "", "7"]
        return ["Mon", "", "Wed", "", "Fri", "", "Sun"]

    def __build_calendar_elements(self, grid_data: Dict[str, Any]) -> List[dict]:
        theme_colors = self._COLOR_THEMES.get(self._color_theme, self._COLOR_THEMES["mp_purple"])
        weeks = grid_data["weeks"]
        week_count = grid_data["week_count"]
        month_labels = grid_data["month_labels"]

        scale_ratio = self._cell_scale / 100
        cell_size = max(10, int(round(13 * scale_ratio)))
        cell_gap = max(0, int(round(self._cell_gap * scale_ratio)))
        row_gap = max(1, int(round(1 * scale_ratio)))
        weekday_col_base = 34 if self._label_style == "english_abbr" else 24
        weekday_col_width = max(20, int(round(weekday_col_base * scale_ratio)))
        auto_cell_width = f"max({self._calendar_min_cell_width}px, calc((100% - {max(0, (week_count - 1) * cell_gap)}px) / {max(1, week_count)}))"
        auto_cell_flex = "none"
        calendar_width = week_count * (cell_size + cell_gap)
        cell_width_value = auto_cell_width if self._calendar_auto_stretch else f"{cell_size}px"
        cell_height_value = f"{cell_size}px"
        radius = f"{self._cell_radius:.1f}px"

        label_cells = []
        if self._show_month_labels:
            for week_index in range(week_count):
                label_cells.append({"component": "div", "props": {"style": {
                    "width": cell_width_value, "flex": auto_cell_flex if self._calendar_auto_stretch else "none", "minWidth": f"{self._calendar_min_cell_width}px" if self._calendar_auto_stretch else f"{cell_size}px", "height": "14px", "fontSize": "10px",
                    "lineHeight": "14px", "color": "rgba(var(--v-theme-on-surface), 0.65)",
                    "marginRight": f"{cell_gap}px", "overflow": "visible", "whiteSpace": "nowrap"}},
                    "text": month_labels.get(week_index, "")})

        weekday_labels = self.__weekday_labels()
        calendar_row_elements = []
        for weekday in range(7):
            row_cells = []
            for week_index in range(week_count):
                cell = weeks[week_index][weekday]
                if self._calendar_auto_stretch:
                    cell_style = {
                        "width": cell_width_value,
                        "flex": "none",
                        "minWidth": f"{self._calendar_min_cell_width}px",
                        "height": "auto",
                        "aspectRatio": "1 / 1",
                        "borderRadius": radius,
                        "backgroundColor": theme_colors[cell["level"]],
                        "marginRight": f"{cell_gap}px",
                        "opacity": 1 if cell["in_range"] else 0,
                        "cursor": "default",
                    }
                else:
                    cell_style = {
                        "width": cell_width_value,
                        "flex": "none",
                        "minWidth": f"{cell_size}px",
                        "height": cell_height_value,
                        "borderRadius": radius,
                        "backgroundColor": theme_colors[cell["level"]],
                        "marginRight": f"{cell_gap}px",
                        "opacity": 1 if cell["in_range"] else 0,
                        "cursor": "default",
                    }
                row_cells.append({"component": "div", "props": {"title": cell["tooltip"] if cell["in_range"] else "", "style": cell_style}})

            label_style = {
                "width": f"{weekday_col_width}px",
                "minWidth": f"{weekday_col_width}px",
                "fontSize": "10px",
                "textAlign": "right",
                "paddingRight": "10px",
                "color": "rgba(var(--v-theme-on-surface), 0.65)",
                "whiteSpace": "nowrap",
            }
            if not self._calendar_auto_stretch:
                label_style["height"] = cell_height_value
                label_style["lineHeight"] = cell_height_value

            calendar_row_elements.append({
                "component": "div",
                "props": {"class": "d-flex align-center", "style": {"marginBottom": f"{row_gap}px", "width": "100%" if self._calendar_auto_stretch else "auto"}},
                "content": [
                    {"component": "div", "props": {"style": label_style}, "text": weekday_labels[weekday]},
                    {"component": "div", "props": {"class": "d-flex align-center", "style": {"flex": "1 1 0", "minWidth": "0"} if self._calendar_auto_stretch else {}}, "content": row_cells}
                ]
            })

        if self._calendar_auto_stretch:
            legend = {
                "component": "div",
                "props": {"class": "d-flex align-center", "style": {
                    "marginTop": "2px", "fontSize": "11px", "color": "rgba(var(--v-theme-on-surface), 0.65)"
                }},
                "content": [
                    {"component": "div", "props": {"style": {"width": f"{weekday_col_width}px", "minWidth": f"{weekday_col_width}px", "paddingRight": "10px"}}},
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center justify-end", "style": {"flex": "1 1 0", "minWidth": "0", "gap": "4px"}},
                        "content": [
                            {"component": "span", "text": "less"},
                            *[{"component": "div", "props": {"style": {
                                "width": auto_cell_width,
                                "minWidth": f"{self._calendar_min_cell_width}px",
                                "height": "auto",
                                "aspectRatio": "1 / 1",
                                "borderRadius": radius,
                                "backgroundColor": theme_colors[level]
                            }}} for level in range(5)],
                            {"component": "span", "text": "more"}
                        ]
                    }
                ]
            }
        else:
            legend = {"component": "div", "props": {"class": "d-flex align-center justify-end", "style": {
                "marginTop": "2px", "gap": "4px", "fontSize": "11px", "color": "rgba(var(--v-theme-on-surface), 0.65)"}},
                      "content": [{"component": "span", "text": "less"}, *[{"component": "div", "props": {"style": {
                          "width": f"{cell_size}px", "height": f"{cell_size}px", "borderRadius": radius,
                          "backgroundColor": theme_colors[level]}}} for level in range(5)], {"component": "span", "text": "more"}]}

        metric_md = 4 if not self._show_date_range else 3
        stats_content = [
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"总入库量：{grid_data['total_count']}"}]},
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"活跃天数：{grid_data['active_days']}"}]},
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"峰值单日：{grid_data['max_count']}"}]}
        ]
        if self._show_date_range:
            stats_content.append({"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"统计区间：{grid_data['date_range']}"}]})

        info_margin = max(0, self._calendar_stretch_row_height)
        stats_margin = "2px" if self._show_legend else f"{info_margin}px"
        legend_margin = f"{info_margin}px"
        stats_row = {"component": "VRow", "props": {"class": "mt-0", "noGutters": True, "style": {"marginTop": stats_margin, "marginBottom": "0"}}, "content": stats_content}
        legend_row = {"component": "VRow", "props": {"class": "mt-0", "noGutters": True, "style": {"marginTop": legend_margin, "marginBottom": "0"}}, "content": [{"component": "VCol", "props": {"cols": 12}, "content": [legend]}]}

        main_calendar_content = [{
            "component": "div",
            "props": {"class": "d-flex align-center", "style": {"marginBottom": "1px"}},
            "content": [
                {"component": "div", "props": {"style": {"width": f"{weekday_col_width}px", "minWidth": f"{weekday_col_width}px"}}},
                {"component": "div", "props": {"class": "d-flex align-center", "style": {"flex": "1 1 0", "minWidth": "0"} if self._calendar_auto_stretch else {}}, "content": label_cells},
            ],
        } if self._show_month_labels else {"component": "div"}, {"component": "div", "content": calendar_row_elements}]

        main_calendar = {
            "component": "div",
            "props": {
                "class": "d-flex",
                "style": {
                    "overflowX": "auto",
                    "marginTop": "-6px",
                    "justifyContent": "stretch" if self._calendar_auto_stretch else ("flex-start" if self._calendar_align == "left" else ("center" if self._calendar_align == "center" else "flex-end"))
                }
            },
            "content": [{"component": "div", "props": {"style": {"width": "100%" if self._calendar_auto_stretch else "auto", "minWidth": "0" if self._calendar_auto_stretch else f"{calendar_width + weekday_col_width + 8}px"}}, "content": main_calendar_content}],
        }

        elements: List[dict] = [main_calendar]
        if self._show_legend:
            elements.append(legend_row)
        if self._show_summary:
            elements.append(stats_row)
        if grid_data["total_count"] == 0:
            elements.append({"component": "VAlert", "props": {"type": "info", "variant": "tonal", "density": "compact", "class": "mt-1"}, "text": "当前统计区间暂无入库数据"})

        return [{"component": "VRow", "content": [{"component": "VCol", "props": {"cols": 12}, "content": elements}]}]

    def __build_performance_elements(self, perf_data: Dict[str, Any], perf_series: Dict[str, List[Any]]) -> List[dict]:
        smooth_cpu = self.__smooth_series(perf_series["cpu"], window=self._performance_smooth_window)
        smooth_memory = self.__smooth_series(perf_series["memory"], window=self._performance_smooth_window)

        perf_chart = {
            "component": "VApexChart",
            "props": {
                "height": self._performance_height,
                "options": {
                    "chart": {"type": "line", "toolbar": {"show": False}, "sparkline": {"enabled": False}},
                    "stroke": {"curve": "smooth", "width": [3, 3]},
                    "xaxis": {
                        "categories": perf_series["categories"],
                        "labels": {"show": False},
                        "axisBorder": {"show": True},
                        "axisTicks": {"show": False}
                    },
                    "yaxis": [
                        {
                            "min": 0,
                            "max": 100,
                            "title": {
                                "text": "CPU %",
                                "style": {
                                    "color": "rgba(var(--v-theme-on-surface), 0.65)",
                                    "fontWeight": "400",
                                    "fontSize": "12px"
                                }
                            },
                            "labels": {
                                "style": {
                                    "colors": ["rgba(var(--v-theme-on-surface), 0.65)"]
                                }
                            }
                        },
                        {
                            "opposite": True,
                            "title": {
                                "text": "内存 MB",
                                "style": {
                                    "color": "rgba(var(--v-theme-on-surface), 0.65)",
                                    "fontWeight": "400",
                                    "fontSize": "12px"
                                }
                            },
                            "labels": {
                                "style": {
                                    "colors": ["rgba(var(--v-theme-on-surface), 0.65)"]
                                }
                            }
                        },
                    ],
                    "colors": [self._performance_cpu_color, self._performance_memory_color],
                    "legend": {"show": False},
                    "dataLabels": {"enabled": False},
                    "grid": {
                        "borderColor": "#9CA3AF33",
                        "strokeDashArray": 4,
                        "xaxis": {"lines": {"show": False}},
                        "yaxis": {"lines": {"show": True}},
                        "padding": {"left": 0, "right": 0}
                    },
                    "tooltip": {"shared": True, "intersect": False},
                    "markers": {"size": 0},
                },
                "series": [
                    {"name": "CPU(%)", "data": smooth_cpu},
                    {"name": "内存(MB)", "data": smooth_memory},
                ],
            },
        }

        summary = {
            "component": "div",
            "props": {
                "class": "d-flex align-center justify-space-between",
                "style": {"marginTop": "4px", "fontSize": "14px", "whiteSpace": "nowrap"},
            },
            "content": [
                {"component": "span", "text": f"CPU：{perf_data['cpu']}%  内存：{perf_data['memory_percent']}%（{perf_data['memory_mb']}MB）"},
                {
                    "component": "div",
                    "props": {"class": "d-flex align-center", "style": {"gap": "6px", "fontSize": "11px", "color": "rgba(var(--v-theme-on-surface), 0.65)"}},
                    "content": [
                        {"component": "span", "text": "CPU"},
                        {"component": "div", "props": {"style": {"width": "10px", "height": "10px", "borderRadius": "2px", "backgroundColor": self._performance_cpu_color}}},
                        {"component": "span", "text": "内存"},
                        {"component": "div", "props": {"style": {"width": "10px", "height": "10px", "borderRadius": "2px", "backgroundColor": self._performance_memory_color}}},
                    ],
                },
            ],
        }

        return [{"component": "VRow", "content": [{"component": "VCol", "props": {"cols": 12}, "content": [perf_chart, summary]}]}]

    def __build_site_statistics_elements(self) -> List[dict]:
        sites = Site.list_order_by_pri() or []
        site_stats = SiteStatistic.list() or []
        site_icons = {str(icon.domain or ""): icon for icon in SiteIcon.list() or []}
        stat_map = {str(item.domain or ""): item for item in site_stats}

        status_label = {
            "connected": "正常",
            "slow": "缓慢",
            "failed": "失败",
            "unknown": "未知",
        }
        status_color = {
            "connected": "success",
            "slow": "warning",
            "failed": "error",
            "unknown": "secondary",
        }

        def _status(stat: Optional[SiteStatistic]) -> str:
            if not stat:
                return "unknown"
            if stat.lst_state == 1:
                return "failed"
            if stat.lst_state == 0:
                if not stat.seconds:
                    return "unknown"
                if stat.seconds >= 5:
                    return "slow"
                return "connected"
            return "unknown"

        rows = []
        connected = slow = failed = unknown = 0
        for site in sites:
            st = stat_map.get(str(site.domain or ""))
            icon = site_icons.get(str(site.domain or ""))
            status = _status(st)
            if status == "connected":
                connected += 1
            elif status == "slow":
                slow += 1
            elif status == "failed":
                failed += 1
            else:
                unknown += 1

            if self._site_stat_only_anomaly and status not in {"slow", "failed"}:
                continue

            success = int(st.success or 0) if st else 0
            fail = int(st.fail or 0) if st else 0
            total = success + fail
            rate = f"{round((success / total) * 100)}%" if total > 0 else "-"
            seconds = int(st.seconds or 0) if st else 0
            seconds_color = "secondary"
            if seconds > 0:
                if seconds < 2:
                    seconds_color = "success"
                elif seconds < 5:
                    seconds_color = "warning"
                else:
                    seconds_color = "error"

            rows.append({
                "component": "VRow",
                "props": {"class": "py-2 px-2", "noGutters": True, "style": {"borderBottom": "1px solid rgba(var(--v-border-color), 0.12)"}},
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 7},
                        "content": [
                            {
                                "component": "div",
                                "props": {"class": "d-flex align-center", "style": {"gap": "8px"}},
                                "content": [
                                    {
                                        "component": "VAvatar",
                                        "props": {"size": 28, "rounded": True, "color": "transparent"},
                                        "content": [
                                            {
                                                "component": "VImg" if (self._site_stat_show_logo and icon and (icon.base64 or icon.url)) else "VIcon",
                                                "props": {"src": icon.base64 if icon and icon.base64 else (icon.url if icon else None), "cover": True} if (self._site_stat_show_logo and icon and (icon.base64 or icon.url)) else {"icon": "mdi-wifi", "size": 18, "color": status_color[status]}
                                            }
                                        ]
                                    },
                                    {
                                        "component": "div",
                                        "content": [
                                            {
                                                "component": "div",
                                                "props": {"class": "d-flex align-center", "style": {"gap": "6px"}},
                                                "content": [
                                                    {"component": "span", "props": {"class": "text-body-2 font-weight-medium"}, "text": site.name or site.domain or "-"},
                                                    {"component": "span", "props": {"class": f"text-caption text-{status_color[status]}", "style": {"lineHeight": "1.2"}}, "text": f"连接{status_label[status]}"}
                                                ]
                                            },
                                            {"component": "div", "props": {"class": "text-caption"}, "text": site.domain or "-"}
                                        ]
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 5},
                        "content": [{
                            "component": "VRow",
                            "props": {"noGutters": True, "class": "text-center"},
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": 6},
                                    "content": [
                                        {"component": "div", "props": {"class": f"text-{seconds_color}"}, "text": f"{seconds}s"},
                                        {"component": "div", "props": {"class": "text-caption"}, "text": "平均耗时"}
                                    ]
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 6},
                                    "content": [
                                        {"component": "div", "props": {"class": "text-body-2"}, "text": rate},
                                        {"component": "div", "props": {"class": "text-caption"}, "text": "成功率"}
                                    ]
                                }
                            ]
                        }]
                    }
                ]
            })

        overview = {
            "component": "VRow",
            "props": {"class": "px-2 pb-2", "noGutters": True},
            "content": [
                {"component": "VCol", "props": {"cols": 3}, "content": [{"component": "div", "props": {"class": "text-caption"}, "text": "总站点"}, {"component": "div", "props": {"class": "text-h6"}, "text": str(len(sites))}]},
                {"component": "VCol", "props": {"cols": 3}, "content": [{"component": "div", "props": {"class": "text-caption"}, "text": "正常站点"}, {"component": "div", "props": {"class": "text-h6 text-success"}, "text": str(connected)}]},
                {"component": "VCol", "props": {"cols": 3}, "content": [{"component": "div", "props": {"class": "text-caption"}, "text": "缓慢站点"}, {"component": "div", "props": {"class": "text-h6 text-warning"}, "text": str(slow)}]},
                {"component": "VCol", "props": {"cols": 3}, "content": [{"component": "div", "props": {"class": "text-caption"}, "text": "失败站点"}, {"component": "div", "props": {"class": "text-h6 text-error"}, "text": str(failed)}]},
            ]
        }

        elements: List[dict] = []
        if self._site_stat_show_overview:
            elements.append(overview)

        header_height = 54
        overview_height = 96 if self._site_stat_show_overview else 0
        available_list_height = max(120, self._site_stat_component_max_height - header_height - overview_height)
        list_visible_height = min(self._site_stat_max_height, available_list_height)

        rows_content = rows if rows else [{"component": "VAlert", "props": {"type": "info", "variant": "tonal", "density": "compact"}, "text": "暂无站点统计数据"}]
        elements.append({
            "component": "div",
            "props": {
                "style": {
                    "maxHeight": f"{self._site_stat_component_max_height}px",
                    "overflow": "hidden"
                }
            },
            "content": [
                {
                    "component": "div",
                    "props": {
                        "style": {
                            "borderTop": "1px solid rgba(var(--v-border-color), 0.28)",
                            "maxHeight": f"{list_visible_height}px",
                            "overflowY": "auto"
                        }
                    },
                    "content": rows_content
                }
            ]
        })

        return [{"component": "VRow", "content": [{"component": "VCol", "props": {"cols": 12}, "content": elements}]}]

    def __build_storage_media_compact_elements(self) -> List[dict]:
        # storage
        total_storage = 0
        used_storage = 0
        try:
            from app.chain.storage import StorageChain
            from app.helper.directory import DirectoryHelper
            dirs = DirectoryHelper().get_dirs()
            storages = set([d.library_storage for d in dirs if d.library_storage]) if dirs else set()
            for _storage in storages:
                usage = StorageChain().storage_usage(_storage)
                if usage:
                    total_storage += usage.total
                    used_storage += usage.total - usage.available
        except Exception:
            pass
        used_percent = round((used_storage / (total_storage or 1)) * 100, 1)

        # media statistic
        movie_count = tv_count = episode_count = user_count = 0
        try:
            from app.chain.dashboard import DashboardChain
            stats = DashboardChain().media_statistic(None) or []
            has_episode = False
            for item in stats:
                movie_count += int(item.movie_count or 0)
                tv_count += int(item.tv_count or 0)
                user_count += int(item.user_count or 0)
                if item.episode_count is not None:
                    episode_count += int(item.episode_count or 0)
                    has_episode = True
            if not has_episode:
                episode_count = -1
        except Exception:
            pass

        compact_media_items = [
            ("电影", f"{movie_count:,}", "mdi-movie-roll", "primary"),
            ("剧集", f"{tv_count:,}", "mdi-television-box", "success"),
            ("集数", "未获取" if episode_count < 0 else f"{episode_count:,}", "mdi-television-classic", "warning"),
            ("用户", f"{user_count:,}", "mdi-account", "info"),
        ]

        return [{
            "component": "VRow",
            "content": [{
                "component": "VCol",
                "props": {"cols": 12},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "pb-1", "style": {"position": "relative", "overflow": "hidden", "borderRadius": "8px", "padding": "4px 8px 6px 8px", "backgroundColor": "rgba(var(--v-theme-surface), 1)", "maxHeight": f"{self._storage_media_height}px"}},
                        "content": [
                            {
                                "component": "div",
                                "props": {
                                    "style": {
                                        "position": "absolute",
                                        "right": "0",
                                        "bottom": "0",
                                        "width": "110px",
                                        "height": "80px",
                                        "background": "transparent"
                                    }
                                }
                            },
                            {"component": "div", "props": {"class": "text-subtitle-1 font-weight-medium", "style": {"lineHeight": "1.2", "marginTop": "-2px", "marginLeft": "0", "paddingLeft": "0"}}, "text": "储存空间"},
                            {"component": "div", "props": {"class": "text-h6 text-primary", "style": {"lineHeight": "1.2", "marginTop": "2px", "marginLeft": "0", "paddingLeft": "0"}}, "text": self.__format_size(total_storage)},
                            {"component": "div", "props": {"class": "text-caption mt-1"}, "text": f"已使用 {used_percent}% 🚀"},
                            {"component": "VProgressLinear", "props": {"modelValue": used_percent, "color": "primary", "height": 8, "rounded": True}}
                        ]
                    },
                    {"component": "VDivider", "props": {"class": "my-1"}},
                    {
                        "component": "div",
                        "content": [
                            {"component": "div", "props": {"class": "text-subtitle-1 font-weight-medium pb-1", "style": {"lineHeight": "1.2", "marginLeft": "0", "paddingLeft": "0"}}, "text": "媒体统计"},
                            {
                                "component": "VRow",
                                "props": {"noGutters": True, "class": "justify-center"},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-1 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center justify-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 42, "class": "me-2 elevation-1", "rounded": "sm", "color": compact_media_items[0][3]}, "content": [{"component": "VIcon", "props": {"size": 24, "color": "white"}, "text": compact_media_items[0][2]}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[0][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[0][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-1 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center justify-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 42, "class": "me-2 elevation-1", "rounded": "sm", "color": compact_media_items[1][3]}, "content": [{"component": "VIcon", "props": {"size": 24, "color": "white"}, "text": compact_media_items[1][2]}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[1][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[1][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-1 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center justify-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 42, "class": "me-2 elevation-1", "rounded": "sm", "color": compact_media_items[2][3]}, "content": [{"component": "VIcon", "props": {"size": 24, "color": "white"}, "text": compact_media_items[2][2]}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[2][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[2][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center justify-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 42, "class": "me-2 elevation-1", "rounded": "sm", "color": compact_media_items[3][3]}, "content": [{"component": "VIcon", "props": {"size": 24, "color": "white"}, "text": compact_media_items[3][2]}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[3][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[3][1]},
                                                ]}
                                            ]}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }]
        }]

    def __build_today_recommend_elements(self) -> List[dict]:
        if self._today_recommend_use_prewarm_pool:
            self.__refresh_today_pool_if_needed()
            pool = self.__pick_today_pool_items()
            logger.info(
                "[dashboardplus:today_recommend] render uses prewarm pool sampled=%s",
                len(pool),
            )
        else:
            pool = self.__load_today_recommend_pool()
        for sample in pool[:5]:
            logger.debug(
                "[dashboardplus:today_recommend] selected_sample mediaid=%s title=%s backdrop=%s",
                sample.get("mediaid"),
                sample.get("title"),
                str(sample.get("backdrop") or "")[:180],
            )
        before_backdrop_filter = len(pool)
        pool = [item for item in pool if self.__is_usable_backdrop(item.get("backdrop"))]
        logger.info(
            "[dashboardplus:today_recommend] carousel candidates=%s usable_backdrop=%s dropped_no_backdrop=%s",
            before_backdrop_filter,
            len(pool),
            max(0, before_backdrop_filter - len(pool)),
        )
        if not pool:
            return [{
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "density": "compact"},
                "text": "暂无可推荐内容",
            }]

        if self._today_recommend_view_mode == "reflective":
            return self.__build_today_recommend_reflective_elements(pool)

        return self.__build_today_recommend_classic_elements(pool)

    def __build_today_recommend_classic_elements(self, pool: List[dict]) -> List[dict]:
        if not pool:
            return [{
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "density": "compact"},
                "text": "暂无可推荐内容",
            }]

        cards: List[dict] = []
        fit_mode = self._today_recommend_image_fit
        if fit_mode == "auto":
            # Auto stretch-fill (no crop): keep full image visible, may leave padding.
            fit_mode = "contain"
        elif fit_mode == "contain":
            # Keep original ratio and avoid enlarging when image is smaller.
            fit_mode = "scale-down"
        img_style: Dict[str, Any] = {
            "position": "absolute",
            "inset": "0",
            "width": "100%",
            "height": "100%",
            "objectFit": fit_mode,
            "objectPosition": "center",
        }
        for media in pool:
            image_url = str(media.get("backdrop") or "").strip()
            image_url = self.__proxy_image_url(image_url)

            cards.append({
                "component": "VCarouselItem",
                "content": [{
                    "component": "a",
                    "props": {
                        "href": self.__build_today_recommend_link(media),
                        "style": {
                            "display": "block",
                            "width": "100%",
                            "height": "100%",
                            "textDecoration": "none",
                            "position": "relative",
                        },
                    },
                    "content": [
                        {
                            "component": "div",
                            "props": {
                                    "style": {
                                        "position": "relative",
                                        "width": "100%",
                                        "height": f"{self._today_recommend_min_height}px",
                                        "overflow": "hidden",
                                    }
                            },
                            "content": [{
                                "component": "img",
                                "props": {
                                    "src": image_url,
                                    "loading": "eager",
                                    "style": img_style
                                },
                            }],
                        },
                        {
                            "component": "div",
                            "props": {
                                "style": {
                                    "position": "absolute",
                                    "left": "0",
                                    "right": "0",
                                    "bottom": "0",
                                    "padding": "10px 12px",
                                    "background": "linear-gradient(180deg, rgba(0, 0, 0, 0) 0%, rgba(0, 0, 0, 0.72) 100%)",
                                    "color": "#FFFFFF",
                                }
                            },
                            "content": [
                                {
                                    "component": "div",
                                    "props": {
                                        "style": {
                                            "fontSize": "16px",
                                            "lineHeight": "1.2",
                                            "fontWeight": 600,
                                            "whiteSpace": "nowrap",
                                            "overflow": "hidden",
                                            "textOverflow": "ellipsis",
                                        }
                                    },
                                    "text": str(media.get("title") or ""),
                                },
                                {
                                    "component": "div",
                                    "props": {
                                        "style": {
                                            "marginTop": "4px",
                                            "fontSize": "12px",
                                            "lineHeight": "1.2",
                                            "opacity": 0.9,
                                            "whiteSpace": "nowrap",
                                            "overflow": "hidden",
                                            "textOverflow": "ellipsis",
                                        }
                                    },
                                    "text": f"{media.get('year') or ''}  {media.get('type') or ''}".strip(),
                                },
                            ],
                        },
                    ],
                }],
            })

        if not cards:
            return [{
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "density": "compact"},
                "text": "暂无可推荐内容",
            }]

        return [{
            "component": "VRow",
            "content": [{
                "component": "VCol",
                "props": {"cols": 12},
                "content": [{
                    "component": "VCarousel",
                    "props": {
                        "cycle": True,
                        "continuous": True,
                        "showArrows": "hover",
                        "hideDelimiters": len(cards) <= 1,
                        "interval": self._today_recommend_speed * 1000,
                        "height": self._today_recommend_min_height,
                    },
                    "content": cards,
                }],
            }],
        }]

    def __build_today_recommend_reflective_elements(self, pool: List[dict]) -> List[dict]:
        if len(pool) < 3:
            logger.info("[dashboardplus:today_recommend] reflective fallback to classic: items<3")
            return self.__build_today_recommend_classic_elements(pool)

        left, center, right = self.__normalize_reflective_ratios(
            self._today_recommend_reflective_ratio_left,
            self._today_recommend_reflective_ratio_center,
            self._today_recommend_reflective_ratio_right,
        )
        if (left, center, right) != (
            self._today_recommend_reflective_ratio_left,
            self._today_recommend_reflective_ratio_center,
            self._today_recommend_reflective_ratio_right,
        ):
            logger.warning("[dashboardplus:today_recommend] invalid ratios fallback to 15/70/15")

        logger.info(
            "[dashboardplus:today_recommend] view_mode=reflective ratios=%s/%s/%s",
            left,
            center,
            right,
        )
        cards: List[dict] = []
        total = len(pool)
        for index in range(total):
            current = pool[index]
            prev_item = pool[(index - 1) % total]
            next_item = pool[(index + 1) % total]

            current_url = self.__proxy_image_url(str(current.get("backdrop") or "").strip())
            prev_url = self.__proxy_image_url(str(prev_item.get("backdrop") or "").strip())
            next_url = self.__proxy_image_url(str(next_item.get("backdrop") or "").strip())

            center_text = f"{current.get('year') or ''}  {current.get('title') or ''}".strip()
            overview = str(current.get("overview") or current.get("summary") or "").strip()

            cards.append({
                "component": "VCarouselItem",
                "content": [{
                    "component": "div",
                    "props": {
                        "class": "dp-reflective-layout",
                        "style": {
                            "position": "relative",
                            "display": "flex",
                            "width": "100%",
                            "height": "100%",
                            "overflow": "hidden",
                            "backgroundColor": "rgba(0,0,0,0.25)",
                        },
                    },
                    "content": [
                        {
                            "component": "div",
                            "props": {
                                "class": "dp-reflective-side dp-reflective-left",
                                "style": {
                                    "position": "relative",
                                    "width": f"{left}%",
                                    "height": "100%",
                                    "overflow": "hidden",
                                },
                            },
                            "content": [
                                {
                                    "component": "img",
                                    "props": {
                                        "src": prev_url,
                                        "loading": "eager",
                                        "style": {
                                            "width": "100%",
                                            "height": "100%",
                                            "objectFit": "cover",
                                        },
                                    },
                                },
                                {
                                    "component": "div",
                                    "props": {
                                        "style": {
                                            "position": "absolute",
                                            "inset": "0",
                                            "background": "linear-gradient(90deg, rgba(255,255,255,0.72) 0%, rgba(255,255,255,0.15) 100%)",
                                        },
                                    },
                                },
                            ],
                        },
                        {
                            "component": "a",
                            "props": {
                                "class": "dp-reflective-center",
                                "href": self.__build_today_recommend_link(current),
                                "style": {
                                    "position": "relative",
                                    "display": "block",
                                    "width": f"{center}%",
                                    "height": "100%",
                                    "textDecoration": "none",
                                    "overflow": "hidden",
                                },
                            },
                            "content": [
                                {
                                    "component": "img",
                                    "props": {
                                        "src": current_url,
                                        "loading": "eager",
                                        "style": {
                                            "width": "100%",
                                            "height": "100%",
                                            "objectFit": "cover",
                                        },
                                    },
                                },
                                {
                                    "component": "div",
                                    "props": {
                                        "class": "dp-reflective-center-overlay",
                                        "style": {
                                            "position": "absolute",
                                            "left": "0",
                                            "right": "0",
                                            "bottom": "0",
                                            "padding": "10px 12px",
                                            "background": "linear-gradient(180deg, rgba(255,255,255,0) 0%, rgba(0,0,0,0.82) 100%)",
                                            "color": "#FFF",
                                            "opacity": 0,
                                            "transition": "opacity 0.22s ease",
                                            "pointerEvents": "none",
                                        },
                                    },
                                    "content": [
                                        {
                                            "component": "div",
                                            "props": {
                                                "style": {
                                                    "fontSize": "14px",
                                                    "fontWeight": 600,
                                                    "whiteSpace": "nowrap",
                                                    "overflow": "hidden",
                                                    "textOverflow": "ellipsis",
                                                },
                                            },
                                            "text": center_text,
                                        },
                                        {
                                            "component": "div",
                                            "props": {
                                                "style": {
                                                    "marginTop": "3px",
                                                    "fontSize": "12px",
                                                    "lineHeight": "1.3",
                                                    "opacity": 0.95,
                                                    "maxHeight": "2.6em",
                                                    "overflow": "hidden",
                                                },
                                            },
                                            "text": overview,
                                        },
                                    ],
                                },
                            ],
                        },
                        {
                            "component": "div",
                            "props": {
                                "class": "dp-reflective-side dp-reflective-right",
                                "style": {
                                    "position": "relative",
                                    "width": f"{right}%",
                                    "height": "100%",
                                    "overflow": "hidden",
                                },
                            },
                            "content": [
                                {
                                    "component": "img",
                                    "props": {
                                        "src": next_url,
                                        "loading": "eager",
                                        "style": {
                                            "width": "100%",
                                            "height": "100%",
                                            "objectFit": "cover",
                                        },
                                    },
                                },
                                {
                                    "component": "div",
                                    "props": {
                                        "style": {
                                            "position": "absolute",
                                            "inset": "0",
                                            "background": "linear-gradient(270deg, rgba(255,255,255,0.72) 0%, rgba(255,255,255,0.15) 100%)",
                                        },
                                    },
                                },
                            ],
                        },
                    ],
                }],
            })

        css_block = (
            ".dp-reflective-carousel .v-window__left,.dp-reflective-carousel .v-window__right{"
            "top:0;height:100%;margin-top:0;transform:none;border-radius:0;"
            "opacity:0;transition:opacity .18s ease;background:rgba(0,0,0,0.16);}"
            ".dp-reflective-carousel .v-window__left{left:0;width:var(--dp-left-zone);justify-content:flex-start;padding-left:10px;}"
            ".dp-reflective-carousel .v-window__right{right:0;width:var(--dp-right-zone);justify-content:flex-end;padding-right:10px;}"
            ".dp-reflective-carousel .v-window__left:hover,.dp-reflective-carousel .v-window__right:hover{opacity:1;}"
            ".dp-reflective-carousel .v-window__left .v-btn,.dp-reflective-carousel .v-window__right .v-btn{"
            "background:rgba(0,0,0,0.35);color:#fff;}"
            ".dp-reflective-carousel .dp-reflective-center:hover .dp-reflective-center-overlay{opacity:1;}"
        )

        return [{
            "component": "VRow",
            "content": [{
                "component": "VCol",
                "props": {"cols": 12},
                "content": [
                    {
                        "component": "style",
                        "text": css_block,
                    },
                    {
                        "component": "VCarousel",
                        "props": {
                            "class": "dp-reflective-carousel",
                            "cycle": True,
                            "continuous": True,
                            "showArrows": "hover",
                            "hideDelimiters": True,
                            "interval": self._today_recommend_speed * 1000,
                            "height": self._today_recommend_min_height,
                            "style": {
                                "borderRadius": "10px",
                                "overflow": "hidden",
                                "--dp-left-zone": f"{left}%",
                                "--dp-right-zone": f"{right}%",
                            },
                        },
                        "content": cards,
                    },
                ],
            }],
        }]

    @staticmethod
    def __build_today_recommend_link(item: Dict[str, Any]) -> str:
        mediaid = quote(str(item.get("mediaid") or ""), safe="")
        title = quote(str(item.get("title") or ""), safe="")
        year = quote(str(item.get("year") or ""), safe="")
        media_type = quote(DashboardPlus.__normalize_media_type_query(item.get("type")), safe="")
        return f"/#/media?mediaid={mediaid}&title={title}&year={year}&type={media_type}"

    @staticmethod
    def __normalize_media_type_query(raw_type: Any) -> str:
        value = str(raw_type or "").strip()
        if not value:
            return ""

        normalized = value.lower()
        movie_values = {
            "movie", "film", "电影", "電影", "影片", "電影片", "mov"
        }
        tv_values = {
            "tv", "tvshow", "series", "show", "电视剧", "電視劇", "剧集", "劇集", "连续剧", "連續劇", "综艺", "綜藝", "anime", "动画", "動畫"
        }

        if normalized in movie_values:
            return "电影"
        if normalized in tv_values:
            return "电视剧"
        return value

    @staticmethod
    def __safe_year_text(raw: Any) -> str:
        if raw is None:
            return ""
        value = str(raw).strip()
        if not value:
            return ""
        if len(value) >= 4 and value[:4].isdigit():
            return value[:4]
        return value

    @staticmethod
    def __normalize_image_url(raw_url: Any) -> str:
        url = str(raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("/"):
            try:
                return settings.TMDB_IMAGE_URL(url)
            except Exception:
                return ""
        return url

    @staticmethod
    def __proxy_image_url(raw_url: Any) -> str:
        url = str(raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("/system/img") or url.startswith("/system/cache/image"):
            return url
        return f"/api/v1/system/cache/image?url={url_quote(url, safe='')}"

    @staticmethod
    def __is_usable_backdrop(raw_url: Any) -> bool:
        url = str(raw_url or "").strip()
        if not url:
            return False
        lower_url = url.lower()
        if not lower_url.startswith("http://") and not lower_url.startswith("https://"):
            return False
        if "doubanio.com" in lower_url or "douban.com" in lower_url:
            return False
        bad_markers = [
            "movie_large.jpg",
            "tv_normal.png",
            "tv_normal.jpg",
            "tv_large.jpg",
            "s_ratio_poster",
            "l_ratio_poster",
            "subject/m/public",
            "imageview2/1/w/500/h/750",
            "imageview2/1/w/600/h/900",
            "w500/h750",
            "w600/h900",
            "w400/h600",
            "w300/h450",
        ]
        if any(marker in lower_url for marker in bad_markers):
            return False

        ratio_patterns = [
            r"/w/?(\d{2,4})/h/?(\d{2,4})",
            r"[?&]w=(\d{2,4})[&].*?[?&]h=(\d{2,4})",
            r"[?&]h=(\d{2,4})[&].*?[?&]w=(\d{2,4})",
        ]
        for pattern in ratio_patterns:
            match = re.search(pattern, lower_url)
            if not match:
                continue
            try:
                w = int(match.group(1))
                h = int(match.group(2))
                if h > int(w * 1.2):
                    return False
            except Exception:
                continue

        return True

    @staticmethod
    def __extract_tmdbid(match_data: Any) -> Optional[int]:
        if not isinstance(match_data, dict):
            return None
        value = match_data.get("id") or match_data.get("tmdb_id") or match_data.get("tmdbid")
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    def __cache_valid(self, ts: float, now_ts: Optional[float] = None) -> bool:
        try:
            current_ts = float(now_ts) if now_ts is not None else datetime.now().timestamp()
            return (current_ts - float(ts)) < self._today_recommend_banner_cache_ttl
        except Exception:
            return False

    @staticmethod
    def __cache_valid_with_ttl(ts: float, ttl: int, now_ts: Optional[float] = None) -> bool:
        try:
            current_ts = float(now_ts) if now_ts is not None else datetime.now().timestamp()
            return (current_ts - float(ts)) < int(ttl)
        except Exception:
            return False

    def __today_result_cache_key(self) -> str:
        return "|".join([
            str(self._today_recommend_source_scope),
            str(self._today_recommend_banner_policy),
            str(self._today_recommend_count),
            str(self._today_recommend_image_fit),
            str(self._today_recommend_banner_fill_limit),
        ])

    def __today_next_refresh_ts(self, now_dt: datetime) -> float:
        try:
            hour, minute = self._today_recommend_prewarm_time.split(":", 1)
            target = now_dt.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
            if target <= now_dt:
                target = target + timedelta(days=1)
            return target.timestamp()
        except Exception:
            fallback = now_dt.replace(hour=8, minute=0, second=0, microsecond=0)
            if fallback <= now_dt:
                fallback = fallback + timedelta(days=1)
            return fallback.timestamp()

    def __today_pool_expired(self) -> bool:
        cache = self._today_recommend_pool_cache if isinstance(self._today_recommend_pool_cache, dict) else {}
        items = cache.get("items") if isinstance(cache, dict) else None
        if not isinstance(items, list) or not items:
            return True
        next_refresh_at = cache.get("next_refresh_at")
        if not isinstance(next_refresh_at, (int, float)):
            return True
        return datetime.now().timestamp() >= float(next_refresh_at)

    def __build_today_prewarm_pool(self) -> List[dict]:
        return self.__load_today_recommend_pool(target_count=self._today_recommend_pool_size, use_result_cache=False)

    def __refresh_today_pool_if_needed(self, force: bool = False):
        if not self._today_recommend_use_prewarm_pool:
            return
        now_dt = datetime.now()
        now_ts = now_dt.timestamp()

        # fast-path checks
        if not force and not self.__today_pool_expired():
            return
        if self._today_pool_refreshing:
            return
        if not force and self._today_pool_last_failed_at and (now_ts - self._today_pool_last_failed_at) < self._today_pool_failure_backoff:
            return

        with self._today_pool_refresh_lock:
            # double-check after acquiring lock
            now_dt = datetime.now()
            now_ts = now_dt.timestamp()
            if self._today_pool_refreshing:
                return
            if not force and not self.__today_pool_expired():
                return
            if not force and self._today_pool_last_failed_at and (now_ts - self._today_pool_last_failed_at) < self._today_pool_failure_backoff:
                return

            self._today_pool_refreshing = True
            logger.info("[dashboardplus:today_recommend] prewarm start force=%s", force)
            start_ts = now_ts
            old_cache = dict(self._today_recommend_pool_cache) if isinstance(self._today_recommend_pool_cache, dict) else {}
            try:
                items = self.__build_today_prewarm_pool()
                if items:
                    next_refresh = self.__today_next_refresh_ts(now_dt)
                    self._today_recommend_pool_cache = {
                        "generated_at": start_ts,
                        "next_refresh_at": next_refresh,
                        "items": items,
                    }
                    self._today_pool_last_failed_at = 0.0
                    cost_ms = int((datetime.now().timestamp() - start_ts) * 1000)
                    logger.info(
                        "[dashboardplus:today_recommend] prewarm done size=%s cost=%sms next_refresh_at=%s",
                        len(items),
                        cost_ms,
                        datetime.fromtimestamp(next_refresh).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                else:
                    logger.warning("[dashboardplus:today_recommend] prewarm produced empty pool, keeping old cache")
                    self._today_recommend_pool_cache = old_cache
                    self._today_pool_last_failed_at = datetime.now().timestamp()
            except Exception as err:
                self._today_recommend_pool_cache = old_cache
                self._today_pool_last_failed_at = datetime.now().timestamp()
                logger.warning("[dashboardplus:today_recommend] prewarm failed, keep old pool: %s", str(err))
            finally:
                self._today_pool_refreshing = False

    def __pick_today_pool_items(self) -> List[dict]:
        cache = self._today_recommend_pool_cache if isinstance(self._today_recommend_pool_cache, dict) else {}
        items = cache.get("items") if isinstance(cache, dict) else None
        if not isinstance(items, list) or not items:
            # startup fallback
            self.__refresh_today_pool_if_needed(force=True)
            cache = self._today_recommend_pool_cache if isinstance(self._today_recommend_pool_cache, dict) else {}
            items = cache.get("items") if isinstance(cache, dict) else None
            if not isinstance(items, list) or not items:
                return []

        candidates = [item for item in items if self.__is_usable_backdrop(item.get("backdrop")) and not self.__is_media_in_library(item)]
        shuffle(candidates)
        return candidates[:self._today_recommend_count]

    def __prune_banner_caches(self):
        self._today_banner_cache_ops = int(getattr(self, "_today_banner_cache_ops", 0)) + 1
        if self._today_banner_cache_ops % 20 != 0:
            return

        now_ts = datetime.now().timestamp()
        self._today_banner_cache = {
            key: value
            for key, value in self._today_banner_cache.items()
            if isinstance(value, dict) and self.__cache_valid(value.get("ts"), now_ts)
        }
        self._today_banner_fail_cache = {
            key: value
            for key, value in self._today_banner_fail_cache.items()
            if self.__cache_valid(value, now_ts)
        }

    @staticmethod
    def __banner_cache_key(item: dict) -> str:
        mediaid = str(item.get("mediaid") or "").strip()
        if mediaid:
            return mediaid

        title = str(item.get("title") or "").strip().lower()
        year = str(item.get("year") or "").strip()
        mtype = str(item.get("type") or "").strip().lower()
        if title:
            return f"fallback:{title}|{year}|{mtype}"
        return ""

    @staticmethod
    def __media_type_for_chain(raw_type: Any) -> Optional[MediaType]:
        normalized_type = DashboardPlus.__normalize_media_type_query(raw_type)
        if normalized_type not in {"电影", "电视剧"}:
            return None
        try:
            return MediaType(normalized_type)
        except Exception:
            return None

    @staticmethod
    def __guess_ids_from_mediaid(mediaid: str) -> Tuple[Optional[str], Optional[str]]:
        value = str(mediaid or "").strip()
        if ":" not in value:
            return None, None
        prefix, mid = value.split(":", 1)
        if not mid:
            return None, None
        source = prefix.strip().lower()
        if source == "tmdb":
            return mid, None
        if source == "douban":
            return None, mid
        return None, None

    def __ensure_banner(self, item: dict) -> dict:
        if not isinstance(item, dict):
            return item
        if not isinstance(getattr(self, "_today_banner_cache", None), dict):
            self._today_banner_cache = {}
        if not isinstance(getattr(self, "_today_banner_fail_cache", None), dict):
            self._today_banner_fail_cache = {}

        self.__prune_banner_caches()

        if str(item.get("backdrop") or "").strip():
            return item
        if self._today_recommend_banner_policy == "existing_only":
            return item

        cache_key = self.__banner_cache_key(item)
        if not cache_key:
            return item

        cached = self._today_banner_cache.get(cache_key)
        if cached:
            cached_ts = cached.get("ts")
            if self.__cache_valid(cached_ts):
                cached_backdrop = str(cached.get("backdrop") or "").strip()
                if cached_backdrop:
                    enriched = dict(item)
                    enriched["backdrop"] = cached_backdrop
                    return enriched
            else:
                self._today_banner_cache.pop(cache_key, None)

        fail_ts = self._today_banner_fail_cache.get(cache_key)
        if fail_ts is not None:
            if self.__cache_valid(fail_ts):
                return item
            self._today_banner_fail_cache.pop(cache_key, None)

        mediaid = str(item.get("mediaid") or "").strip()
        tmdb_id = item.get("tmdb_id")
        douban_id = item.get("douban_id")
        if mediaid and not tmdb_id and not douban_id:
            guessed_tmdb, guessed_douban = self.__guess_ids_from_mediaid(mediaid)
            tmdb_id = tmdb_id or guessed_tmdb
            douban_id = douban_id or guessed_douban

        if not tmdb_id and not douban_id and self._today_recommend_banner_policy != "enhanced":
            self._today_banner_fail_cache[cache_key] = datetime.now().timestamp()
            return item

        try:
            mediachain = MediaChain()
            meta = None
            if not tmdb_id and not douban_id and self._today_recommend_banner_policy == "enhanced":
                title = str(item.get("title") or "").strip()
                if title:
                    year = str(item.get("year") or "").strip()
                    subtitle = year if year else ""
                    meta = MetaInfo(title=title, subtitle=subtitle)
            media_type = self.__media_type_for_chain(item.get("type"))
            mediainfo = mediachain.recognize_media(
                meta=meta,
                tmdbid=tmdb_id,
                doubanid=douban_id,
                mtype=media_type,
            )
            if mediainfo:
                mediachain.obtain_images(mediainfo)
                backdrop = ""
                get_backdrop_image = getattr(mediainfo, "get_backdrop_image", None)
                if callable(get_backdrop_image):
                    backdrop = str(get_backdrop_image() or "").strip()
                if not backdrop:
                    backdrop = str(getattr(mediainfo, "backdrop_path", "") or "").strip()
                backdrop = self.__normalize_image_url(backdrop)
                if self.__is_usable_backdrop(backdrop):
                    self._today_banner_cache[cache_key] = {
                        "backdrop": backdrop,
                        "ts": datetime.now().timestamp(),
                    }
                    self._today_banner_fail_cache.pop(cache_key, None)
                    enriched = dict(item)
                    enriched["backdrop"] = backdrop
                    return enriched

            # Douban items may have only poster-like images; fallback to title/year recognition once.
            if douban_id and not tmdb_id:
                title = str(item.get("title") or "").strip()
                if title:
                    year = str(item.get("year") or "").strip()
                    fallback_meta = MetaInfo(title=title, subtitle=year if year else "")
                    fallback_info = mediachain.recognize_media(
                        meta=fallback_meta,
                        mtype=media_type,
                    )
                    if fallback_info:
                        mediachain.obtain_images(fallback_info)
                        fallback_backdrop = ""
                        fallback_getter = getattr(fallback_info, "get_backdrop_image", None)
                        if callable(fallback_getter):
                            fallback_backdrop = str(fallback_getter() or "").strip()
                        if not fallback_backdrop:
                            fallback_backdrop = str(getattr(fallback_info, "backdrop_path", "") or "").strip()
                        fallback_backdrop = self.__normalize_image_url(fallback_backdrop)
                        if self.__is_usable_backdrop(fallback_backdrop):
                            self._today_banner_cache[cache_key] = {
                                "backdrop": fallback_backdrop,
                                "ts": datetime.now().timestamp(),
                            }
                            self._today_banner_fail_cache.pop(cache_key, None)
                            enriched = dict(item)
                            enriched["backdrop"] = fallback_backdrop
                            return enriched

                    # Douban entry fallback: force TMDB match then obtain images.
                    tmdb_match = mediachain.match_tmdbinfo(
                        name=title,
                        mtype=media_type,
                        year=year or None,
                    )
                    tmdb_match_id = self.__extract_tmdbid(tmdb_match)
                    if tmdb_match_id:
                        tmdb_info = mediachain.recognize_media(
                            tmdbid=tmdb_match_id,
                            mtype=media_type,
                        )
                        if tmdb_info:
                            mediachain.obtain_images(tmdb_info)
                            tmdb_backdrop = ""
                            tmdb_getter = getattr(tmdb_info, "get_backdrop_image", None)
                            if callable(tmdb_getter):
                                tmdb_backdrop = str(tmdb_getter() or "").strip()
                            if not tmdb_backdrop:
                                tmdb_backdrop = str(getattr(tmdb_info, "backdrop_path", "") or "").strip()
                            tmdb_backdrop = self.__normalize_image_url(tmdb_backdrop)
                            if self.__is_usable_backdrop(tmdb_backdrop):
                                self._today_banner_cache[cache_key] = {
                                    "backdrop": tmdb_backdrop,
                                    "ts": datetime.now().timestamp(),
                                }
                                self._today_banner_fail_cache.pop(cache_key, None)
                                enriched = dict(item)
                                enriched["backdrop"] = tmdb_backdrop
                                return enriched
        except Exception:
            pass

        self._today_banner_fail_cache[cache_key] = datetime.now().timestamp()
        return item

    def __fetch_today_recommend_sources(self) -> List[dict]:
        chain = RecommendChain()
        items: List[dict] = []

        source_calls: List[Tuple[str, Any]] = []
        if self._today_recommend_source_scope in {"all", "imdb"}:
            source_calls.append(("tmdb_trending", lambda: chain.tmdb_trending(page=1)))
        if self._today_recommend_source_scope in {"all", "douban"}:
            source_calls.extend([
                ("douban_movie_showing", lambda: chain.douban_movie_showing(page=1, count=30)),
                ("douban_movies", lambda: chain.douban_movies(page=1, count=30)),
                ("douban_tvs", lambda: chain.douban_tvs(page=1, count=30)),
            ])

        for source_name, fetch_source in source_calls:
            try:
                source_items = fetch_source() or []
                for raw in source_items:
                    if isinstance(raw, dict):
                        payload = dict(raw)
                        payload["_recommend_source"] = source_name
                        items.append(payload)
            except Exception:
                continue

        return items

    def __match_scope_filter(self, item: dict) -> bool:
        if self._today_recommend_source_scope != "imdb":
            return True
        return bool(item.get("tmdb_id") or item.get("imdb_id"))

    def __normalize_recommend_item(self, raw: dict) -> Optional[dict]:
        if not isinstance(raw, dict):
            return None

        recommend_source = str(raw.get("_recommend_source") or "")

        tmdb_id = raw.get("tmdb_id") or raw.get("tmdbid")
        douban_id = raw.get("douban_id") or raw.get("doubanid")
        imdb_id = raw.get("imdb_id") or raw.get("imdbid")
        mediaid = ""
        if tmdb_id:
            mediaid = f"tmdb:{tmdb_id}"
        elif douban_id:
            mediaid = f"douban:{douban_id}"
        elif imdb_id:
            mediaid = f"imdb:{imdb_id}"

        title = str(raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        if not mediaid and self._today_recommend_banner_policy != "enhanced":
            return None

        year = self.__safe_year_text(raw.get("year") or raw.get("release_date") or raw.get("first_air_date"))
        mtype = str(raw.get("type") or "").strip()

        backdrop = self.__normalize_image_url(raw.get("backdrop") or raw.get("backdrop_path"))
        # Douban-source entries should never trust native backdrop; force enrichment from non-douban providers.
        if recommend_source.startswith("douban"):
            backdrop = ""
        poster = self.__normalize_image_url(raw.get("poster") or raw.get("poster_path"))

        return {
            "mediaid": mediaid,
            "title": title,
            "year": year,
            "type": mtype,
            "backdrop": backdrop,
            "poster": poster,
            "tmdb_id": tmdb_id,
            "douban_id": douban_id,
            "imdb_id": imdb_id,
            "source": recommend_source,
        }

    def __is_media_in_library(self, item: dict) -> bool:
        tmdb_id = item.get("tmdb_id")
        douban_id = item.get("douban_id")
        subscribe_oper = SubscribeOper()
        transfer_oper = TransferHistoryOper()
        mtype = self.__normalize_media_type_query(item.get("type"))
        title = str(item.get("title") or "").strip()
        year = str(item.get("year") or "").strip()

        if tmdb_id:
            if subscribe_oper.exists(tmdbid=tmdb_id):
                return True
            if subscribe_oper.exist_history(tmdbid=tmdb_id):
                return True
            if transfer_oper.get_by_type_tmdbid(mtype=mtype, tmdbid=tmdb_id):
                return True

        if douban_id:
            if subscribe_oper.exists(doubanid=douban_id):
                return True
            if subscribe_oper.exist_history(doubanid=douban_id):
                return True

        if title and year and mtype:
            if transfer_oper.get_by(title=title, year=year, mtype=mtype):
                return True

        return False

    def __load_today_recommend_pool(self, target_count: Optional[int] = None, use_result_cache: bool = True) -> List[dict]:
        count = int(target_count) if isinstance(target_count, int) and target_count > 0 else self._today_recommend_count
        cache_key = f"{self.__today_result_cache_key()}|{count}"
        if use_result_cache:
            cached = self._today_result_cache.get(cache_key)
            if isinstance(cached, dict) and self.__cache_valid_with_ttl(cached.get("ts"), self._today_recommend_result_ttl):
                cached_items = cached.get("items")
                if isinstance(cached_items, list) and cached_items:
                    logger.info(
                        "[dashboardplus:today_recommend] result_cache hit key=%s size=%s",
                        cache_key,
                        len(cached_items),
                    )
                    return cached_items

        raw_items = self.__fetch_today_recommend_sources()
        raw_count = len(raw_items)
        normalized_items: List[dict] = []
        for raw in raw_items:
            item = self.__normalize_recommend_item(raw)
            if item and self.__match_scope_filter(item):
                normalized_items.append(item)

        normalized_count = len(normalized_items)

        unique_items: List[dict] = []
        seen_keys = set()
        for item in normalized_items:
            mediaid = str(item.get("mediaid") or "").strip()
            if mediaid:
                dedupe_key = f"mediaid:{mediaid}"
            else:
                title = str(item.get("title") or "").strip().lower()
                year = str(item.get("year") or "").strip()
                mtype = str(item.get("type") or "").strip().lower()
                dedupe_key = f"fallback:{title}|{year}|{mtype}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            unique_items.append(item)

        unique_count = len(unique_items)

        pool: List[dict] = []
        in_library_filtered = 0
        for item in unique_items:
            if not self.__is_media_in_library(item):
                pool.append(item)
            else:
                in_library_filtered += 1

        candidate_after_library = len(pool)

        shuffle(pool)
        logger.info(
            "[dashboardplus:today_recommend] source_scope=%s raw=%s normalized=%s deduped=%s filtered_in_library=%s post_library=%s target_count=%s",
            self._today_recommend_source_scope,
            raw_count,
            normalized_count,
            unique_count,
            in_library_filtered,
            candidate_after_library,
            count,
        )

        if self._today_recommend_banner_policy == "existing_only":
            selected = []
            for item in pool:
                if self.__is_usable_backdrop(item.get("backdrop")):
                    selected.append(item)
                if len(selected) >= count:
                    break
            missing_backdrop = max(0, count - len(selected))
            logger.info(
                "[dashboardplus:today_recommend] banner_policy=%s selected_missing_backdrop=%s",
                self._today_recommend_banner_policy,
                missing_backdrop,
            )
            self._today_result_cache[cache_key] = {
                "ts": datetime.now().timestamp(),
                "items": selected,
            }
            return selected

        filled = 0
        output: List[dict] = []
        for item in pool:
            current = item
            if not self.__is_usable_backdrop(current.get("backdrop")) and filled < self._today_recommend_banner_fill_limit:
                current = self.__ensure_banner(current)
                filled += 1
            if self.__is_usable_backdrop(current.get("backdrop")):
                output.append(current)
            if len(output) >= count:
                break

        missing_backdrop = max(0, count - len(output))
        logger.info(
            "[dashboardplus:today_recommend] banner_policy=%s fill_attempted=%s missing_backdrop_after_enrich=%s",
            self._today_recommend_banner_policy,
            filled,
            missing_backdrop,
        )
        self._today_result_cache[cache_key] = {
            "ts": datetime.now().timestamp(),
            "items": output,
        }
        return output

    @staticmethod
    def __format_size(size_bytes: float) -> str:
        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = float(size_bytes or 0)
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        return f"{size:.2f} {units[unit_index]}"

    @staticmethod
    def __smooth_series(values: List[float], window: int = 5) -> List[float]:
        if window <= 1 or not values:
            return values
        smoothed: List[float] = []
        for idx in range(len(values)):
            start = max(0, idx - window + 1)
            segment = values[start:idx + 1]
            smoothed.append(round(sum(segment) / len(segment), 2))
        return smoothed
