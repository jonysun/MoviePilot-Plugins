import math
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db.models.site import Site
from app.db.models.siteicon import SiteIcon
from app.db.models.sitestatistic import SiteStatistic
from app.db.transferhistory_oper import TransferHistoryOper
from app.plugins import _PluginBase
from app.utils.system import SystemUtils


class DashboardPlus(_PluginBase):
    plugin_name = "仪表板增强"
    plugin_desc = "提供入库日历、主机性能、站点统计、存储媒体组合四类仪表板组件。"
    plugin_icon = "statistic.png"
    plugin_version = "1.0.3"
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
    _performance_cpu_color_preset: str = "purple"
    _performance_memory_color_preset: str = "blue"
    _performance_cpu_color: str = "#9155FD"
    _performance_memory_color: str = "#16B1FF"

    # site statistics settings
    _site_stat_size: str = "full"
    _site_stat_refresh: int = 300
    _site_stat_show_overview: bool = True
    _site_stat_show_logo: bool = True
    _site_stat_max_height: int = 460

    # storage + media compact settings
    _storage_media_size: str = "half"
    _storage_media_refresh: int = 300

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
        self._site_stat_max_height = self.__safe_refresh(config.get("site_stat_max_height", 460), 300, 900)

        self._storage_media_refresh = self.__safe_refresh(config.get("storage_media_refresh", 300), 10, 3600)
        self._summary_spacing = self.__safe_refresh(config.get("summary_spacing", 8), 0, 40)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        # 日历与主机性能完全复用现有配置结构，再补充 C/D 组件配置
        form_content = [
            {
                "component": "VRow",
                "props": {"style": {"marginTop": "0px"}},
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 6},
                        "content": [{"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}}]
                    },
                    {
                        "component": "VCol",
                        "props": {"cols": 12, "md": 6},
                        "content": [{"component": "VSwitch", "props": {"model": "show_summary", "label": "显示摘要信息"}}]
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
                            {"component": "VExpansionPanelTitle", "text": "日历图设置"},
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
                                                        "label": "日历组件宽度",
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
                                                        "label": "日历自动刷新（秒）",
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
                                                        "placeholder": "110"
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
                                                        "label": "日历本体对齐",
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
                                                    "props": {"model": "show_date_range", "label": "显示统计区间"}
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
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VSelect", "props": {"model": "performance_cpu_color_preset", "label": "CPU折线颜色", "items": [{"title": "紫色", "value": "purple"}, {"title": "红色", "value": "red"}, {"title": "橙色", "value": "orange"}, {"title": "绿色", "value": "green"}, {"title": "蓝色", "value": "blue"}]}}]},
                                            {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "VSelect", "props": {"model": "performance_memory_color_preset", "label": "内存折线颜色", "items": [{"title": "蓝色", "value": "blue"}, {"title": "紫色", "value": "purple"}, {"title": "红色", "value": "red"}, {"title": "橙色", "value": "orange"}, {"title": "绿色", "value": "green"}]}}]}
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
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSwitch", "props": {"model": "site_stat_show_overview", "label": "显示统计概览"}}]},
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VSwitch", "props": {"model": "site_stat_show_logo", "label": "显示站点Logo"}}]}
                                    ]
                                }, {
                                    "component": "VRow",
                                    "content": [
                                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [{"component": "VTextField", "props": {"model": "site_stat_max_height", "label": "站点列表可视高度", "type": "number", "min": 300, "max": 900, "placeholder": "460"}}]}
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
                                        {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [{"component": "VTextField", "props": {"model": "storage_media_refresh", "label": "刷新间隔（秒）", "type": "number", "min": 10, "max": 3600, "placeholder": "300"}}]}
                                    ]
                                }, {
                                    "component": "VRow",
                                    "content": [
                                        {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [{"component": "VTextField", "props": {"model": "summary_spacing", "label": "日历统计行上边距（0-40）", "type": "number", "min": 0, "max": 40, "placeholder": "8"}}]}
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
            "dashboard_size": self._calendar_size,
            "calendar_size": self._calendar_size,
            "performance_size": self._performance_size,
            "site_stat_size": self._site_stat_size,
            "storage_media_size": self._storage_media_size,
            "cell_scale": self._cell_scale,
            "cell_gap": self._cell_gap,
            "cell_radius": self._cell_radius,
            "range": self._range,
            "label_style": self._label_style,
            "calendar_refresh": self._calendar_refresh,
            "performance_height": self._performance_height,
            "performance_refresh": self._performance_refresh,
            "performance_window": self._performance_window,
            "performance_cpu_color_preset": self._performance_cpu_color_preset,
            "performance_memory_color_preset": self._performance_memory_color_preset,
            "site_stat_refresh": self._site_stat_refresh,
            "site_stat_show_overview": self._site_stat_show_overview,
            "site_stat_show_logo": self._site_stat_show_logo,
            "site_stat_max_height": self._site_stat_max_height,
            "storage_media_refresh": self._storage_media_refresh,
            "summary_spacing": self._summary_spacing,
        }

    def get_page(self) -> List[dict]:
        return [{
            "component": "div",
            "props": {"class": "text-center"},
            "text": "请在仪表板中添加“媒体入库日历图 / 主机性能 / 站点统计 / 储存情况与媒体统计”组件查看。"
        }]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [
            {"key": "calendar", "name": "媒体入库日历图"},
            {"key": "performance", "name": "主机性能"},
            {"key": "site_statistics", "name": "站点统计"},
            {"key": "storage_media_compact", "name": "储存情况与媒体统计"},
        ]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        if key and key not in {"calendar", "performance", "site_statistics", "storage_media_compact"}:
            return None

        key = key or "calendar"
        cols = {"cols": 12}
        attrs = {"refresh": self._calendar_refresh, "title": "媒体入库日历图", "border": True}

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
            else:
                cols = self._SIZE_COLS.get(self._calendar_size, self._SIZE_COLS["two_third"])
                attrs = {"refresh": self._calendar_refresh, "title": "媒体入库日历图", "border": True}
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
            return ["周一", "", "周三", "", "周五", "", ""]
        if self._label_style == "numeric":
            return ["1", "", "3", "", "5", "", ""]
        return ["Mon", "", "Wed", "", "Fri", "", ""]

    def __build_calendar_elements(self, grid_data: Dict[str, Any]) -> List[dict]:
        theme_colors = self._COLOR_THEMES.get(self._color_theme, self._COLOR_THEMES["mp_purple"])
        weeks = grid_data["weeks"]
        week_count = grid_data["week_count"]
        month_labels = grid_data["month_labels"]

        scale_ratio = self._cell_scale / 100
        cell_size = max(10, int(round(13 * scale_ratio)))
        cell_gap = max(0, int(round(self._cell_gap * scale_ratio)))
        row_gap = max(1, int(round(1 * scale_ratio)))
        weekday_col_base = 30 if self._label_style == "english_abbr" else 22
        weekday_col_width = max(20, int(round(weekday_col_base * scale_ratio)))
        calendar_width = week_count * (cell_size + cell_gap)
        radius = f"{self._cell_radius:.1f}px"

        label_cells = []
        if self._show_month_labels:
            for week_index in range(week_count):
                label_cells.append({"component": "div", "props": {"style": {
                    "width": f"{cell_size}px", "minWidth": f"{cell_size}px", "height": "14px", "fontSize": "10px",
                    "lineHeight": "14px", "color": "rgba(var(--v-theme-on-surface), 0.65)",
                    "marginRight": f"{cell_gap}px", "overflow": "visible", "whiteSpace": "nowrap"}},
                    "text": month_labels.get(week_index, "")})

        weekday_labels = self.__weekday_labels()
        weekday_label_elements = []
        day_row_elements = []
        for weekday in range(7):
            row_cells = []
            for week_index in range(week_count):
                cell = weeks[week_index][weekday]
                row_cells.append({"component": "div", "props": {"title": cell["tooltip"] if cell["in_range"] else "", "style": {
                    "width": f"{cell_size}px", "minWidth": f"{cell_size}px", "height": f"{cell_size}px",
                    "borderRadius": radius, "backgroundColor": theme_colors[cell["level"]],
                    "marginRight": f"{cell_gap}px", "opacity": 1 if cell["in_range"] else 0, "cursor": "default"}}})

            weekday_label_elements.append({"component": "div", "props": {"style": {
                "width": f"{weekday_col_width}px", "minWidth": f"{weekday_col_width}px", "height": f"{cell_size}px",
                "lineHeight": f"{cell_size}px", "marginBottom": f"{row_gap}px", "fontSize": "10px", "textAlign": "right",
                "paddingRight": "4px", "color": "rgba(var(--v-theme-on-surface), 0.65)", "whiteSpace": "nowrap"}},
                "text": weekday_labels[weekday]})

            day_row_elements.append({"component": "div", "props": {"class": "d-flex align-center", "style": {"marginBottom": f"{row_gap}px"}}, "content": row_cells})

        legend = {"component": "div", "props": {"class": "d-flex align-center justify-end", "style": {
            "marginTop": "2px", "gap": "4px", "fontSize": "11px", "color": "rgba(var(--v-theme-on-surface), 0.65)"}},
                  "content": [{"component": "span", "text": "less"}, *[{"component": "div", "props": {"style": {
                      "width": f"{cell_size}px", "height": f"{cell_size}px", "borderRadius": radius,
                      "backgroundColor": theme_colors[level]}}} for level in range(5)], {"component": "span", "text": "more"}]}

        metric_md = 3 if (self._show_legend and not self._show_date_range) else (4 if not self._show_date_range else 3)
        stats_content = [
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"总入库量：{grid_data['total_count']}"}]},
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"活跃天数：{grid_data['active_days']}"}]},
            {"component": "VCol", "props": {"cols": 12, "md": metric_md}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"峰值单日：{grid_data['max_count']}"}]}
        ]
        if self._show_date_range:
            stats_content.append({"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{"component": "div", "props": {"style": {"fontSize": "11px", "lineHeight": "1.2", "color": "rgba(var(--v-theme-on-surface), 0.65)"}}, "text": f"统计区间：{grid_data['date_range']}"}]})
        if self._show_legend:
            stats_content.append({"component": "VCol", "props": {"cols": 12, "md": 12 if self._show_date_range else 3}, "content": [legend]})

        stats_row = {"component": "VRow", "props": {"class": "mt-0", "noGutters": True, "style": {"marginTop": f"{self._summary_spacing}px", "marginBottom": "0"}}, "content": stats_content}

        main_calendar_content = [{
            "component": "div",
            "props": {"class": "d-flex align-center", "style": {"marginBottom": "1px"}},
            "content": [
                {"component": "div", "props": {"style": {"width": f"{weekday_col_width}px", "minWidth": f"{weekday_col_width}px"}}},
                {"component": "div", "props": {"class": "d-flex align-center"}, "content": label_cells},
            ],
        } if self._show_month_labels else {"component": "div"}, {"component": "div", "props": {"class": "d-flex"}, "content": [{"component": "div", "content": weekday_label_elements}, {"component": "div", "content": day_row_elements}]}]

        main_calendar = {
            "component": "div",
            "props": {
                "class": "d-flex",
                "style": {
                    "overflowX": "auto",
                    "marginTop": "-6px",
                    "justifyContent": "flex-start" if self._calendar_align == "left" else ("center" if self._calendar_align == "center" else "flex-end")
                }
            },
            "content": [{"component": "div", "props": {"style": {"minWidth": f"{calendar_width + weekday_col_width + 8}px"}}, "content": main_calendar_content}],
        }

        elements: List[dict] = [main_calendar]
        if self._show_summary:
            elements.append(stats_row)
        if grid_data["total_count"] == 0:
            elements.append({"component": "VAlert", "props": {"type": "info", "variant": "tonal", "density": "compact", "class": "mt-1"}, "text": "当前统计区间暂无入库数据"})

        return [{"component": "VRow", "content": [{"component": "VCol", "props": {"cols": 12}, "content": elements}]}]

    def __build_performance_elements(self, perf_data: Dict[str, Any], perf_series: Dict[str, List[Any]]) -> List[dict]:
        smooth_cpu = self.__smooth_series(perf_series["cpu"], window=5)
        smooth_memory = self.__smooth_series(perf_series["memory"], window=5)

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
                        {"min": 0, "max": 100, "title": {"text": "CPU %"}},
                        {"opposite": True, "title": {"text": "内存 MB"}},
                    ],
                    "colors": [self._performance_cpu_color, self._performance_memory_color],
                    "legend": {"show": False},
                    "dataLabels": {"enabled": False},
                    "grid": {
                        "xaxis": {"lines": {"show": False}},
                        "yaxis": {"lines": {"show": False}},
                        "padding": {"left": 0, "right": 0}
                    },
                    "tooltip": {"shared": True, "intersect": False},
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
                                                    {"component": "span", "props": {"class": f"text-{status_color[status]}"}, "text": f"连接{status_label[status]}"}
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

        table_header = [
            {"component": "VDivider"},
            {"component": "VRow", "props": {"class": "px-2 py-1", "noGutters": True}, "content": [
                {"component": "VCol", "props": {"cols": 7}, "text": "站点"},
                {"component": "VCol", "props": {"cols": 5}, "text": "统计信息"},
            ]},
            {"component": "VDivider"}
        ]
        rows_content = rows if rows else [{"component": "VAlert", "props": {"type": "info", "variant": "tonal", "density": "compact"}, "text": "暂无站点统计数据"}]
        elements.append({
            "component": "div",
            "props": {
                "style": {
                    "maxHeight": f"{self._site_stat_max_height}px",
                    "overflow": "hidden"
                }
            },
            "content": [
                {"component": "div", "content": table_header},
                {
                    "component": "div",
                    "props": {
                        "style": {
                            "maxHeight": f"{max(120, self._site_stat_max_height - 54)}px",
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
                        "props": {"class": "pb-2", "style": {"position": "relative", "overflow": "hidden", "borderRadius": "8px", "padding": "8px", "backgroundColor": "rgba(var(--v-theme-surface), 1)"}},
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
                            {"component": "div", "props": {"class": "text-subtitle-1 font-weight-medium"}, "text": "储存空间"},
                            {"component": "div", "props": {"class": "text-h6 text-primary"}, "text": self.__format_size(total_storage)},
                            {"component": "div", "props": {"class": "text-caption mt-1"}, "text": f"已使用 {used_percent}% 🚀"},
                            {"component": "VProgressLinear", "props": {"modelValue": used_percent, "color": "primary", "height": 8, "rounded": True}}
                        ]
                    },
                    {"component": "VDivider", "props": {"class": "my-2"}},
                    {
                        "component": "div",
                        "content": [
                            {"component": "div", "props": {"class": "text-subtitle-1 font-weight-medium pb-2"}, "text": "媒体统计"},
                            {
                                "component": "VRow",
                                "props": {"noGutters": True},
                                "content": [
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-2 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 36, "class": "me-2", "rounded": "sm", "style": {"backgroundColor": f"rgba(var(--v-theme-{compact_media_items[0][3]}), 0.16)"}}, "content": [{"component": "VIcon", "props": {"icon": compact_media_items[0][2], "size": 20, "color": compact_media_items[0][3]}}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[0][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[0][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-2 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 36, "class": "me-2", "rounded": "sm", "style": {"backgroundColor": f"rgba(var(--v-theme-{compact_media_items[1][3]}), 0.16)"}}, "content": [{"component": "VIcon", "props": {"icon": compact_media_items[1][2], "size": 20, "color": compact_media_items[1][3]}}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[1][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[1][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-2 pe-1"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 36, "class": "me-2", "rounded": "sm", "style": {"backgroundColor": f"rgba(var(--v-theme-{compact_media_items[2][3]}), 0.16)"}}, "content": [{"component": "VIcon", "props": {"icon": compact_media_items[2][2], "size": 20, "color": compact_media_items[2][3]}}]},
                                                {"component": "div", "content": [
                                                    {"component": "div", "props": {"class": "text-caption"}, "text": compact_media_items[2][0]},
                                                    {"component": "div", "props": {"class": "text-h6"}, "text": compact_media_items[2][1]},
                                                ]}
                                            ]}
                                        ]
                                    },
                                    {
                                        "component": "VCol",
                                        "props": {"cols": 3, "class": "py-2"},
                                        "content": [
                                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                                {"component": "VAvatar", "props": {"size": 36, "class": "me-2", "rounded": "sm", "style": {"backgroundColor": f"rgba(var(--v-theme-{compact_media_items[3][3]}), 0.16)"}}, "content": [{"component": "VIcon", "props": {"icon": compact_media_items[3][2], "size": 20, "color": compact_media_items[3][3]}}]},
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
