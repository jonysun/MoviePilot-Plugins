import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db.transferhistory_oper import TransferHistoryOper
from app.plugins import _PluginBase
from app.utils.system import SystemUtils


class MediaCalendar(_PluginBase):
    plugin_name = "媒体入库日历图"
    plugin_desc = "以贡献日历风格展示入库活跃度与性能走势。"
    plugin_icon = "statistic.png"
    plugin_version = "1.2.3"
    plugin_author = "jonysun"
    author_url = "https://github.com/jonysun"
    plugin_config_prefix = "mediacalendar_"
    plugin_order = 99
    auth_level = 1

    _enabled: bool = True
    _refresh: int = 300

    # calendar settings
    _show_summary: bool = True
    _color_theme: str = "mp_purple"
    _show_month_labels: bool = True
    _calendar_size: str = "two_third"
    _cell_scale: int = 100
    _range: str = "1y"

    # performance settings
    _performance_size: str = "half"
    _performance_height: int = 190

    _MONTH_ABBR: List[str] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

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

    def init_plugin(self, config: dict = None):
        config = config or {}
        enabled_value = config.get("enabled")
        if enabled_value is None:
            enabled_value = config.get("enable", True)
        self._enabled = self.__to_bool(enabled_value, default=True)
        self._refresh = self.__safe_refresh(config.get("refresh", 300))

        self._show_summary = self.__to_bool(config.get("show_summary", True), default=True)

        self._color_theme = config.get("color_theme", "mp_purple")
        if self._color_theme not in self._COLOR_THEMES:
            self._color_theme = "mp_purple"

        self._show_month_labels = self.__to_bool(config.get("show_month_labels", True), default=True)

        dashboard_size = config.get("dashboard_size", "two_third")
        self._calendar_size = config.get("calendar_size", dashboard_size)
        if self._calendar_size not in self._SIZE_COLS:
            self._calendar_size = "two_third"

        self._performance_size = config.get("performance_size", "half")
        if self._performance_size not in self._SIZE_COLS:
            self._performance_size = "half"

        self._cell_scale = self.__safe_scale(config.get("cell_scale", 100))

        self._range = config.get("range", "1y")
        if self._range not in self._RANGE_DAYS:
            self._range = "1y"

        self._performance_height = self.__safe_perf_height(config.get("performance_height", 190))

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [{
            "component": "VForm",
            "content": [
                {
                    "component": "VRow",
                    "props": {
                        "style": {
                            "marginTop": "0px"
                        }
                    },
                    "content": [
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {
                                    "component": "VSwitch",
                                    "props": {"model": "enabled", "label": "启用插件"}
                                }
                            ]
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {
                                    "component": "VSwitch",
                                    "props": {"model": "show_summary", "label": "显示摘要信息"}
                                }
                            ]
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {
                                    "component": "VTextField",
                                    "props": {
                                        "model": "refresh",
                                        "label": "自动刷新间隔（秒）",
                                        "type": "number",
                                        "min": 30,
                                        "placeholder": "300"
                                    }
                                }
                            ]
                        }
                    ]
                },
                {
                    "component": "VExpansionPanels",
                    "props": {
                        "variant": "accordion",
                        "multiple": True
                    },
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
                                                            "model": "cell_scale",
                                                            "label": "格子尺寸缩放（80-130%）",
                                                            "type": "number",
                                                            "min": 80,
                                                            "max": 130,
                                                            "placeholder": "100"
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
                                                    "props": {"cols": 12, "md": 4},
                                                    "content": [{
                                                        "component": "VSwitch",
                                                        "props": {
                                                            "model": "show_month_labels",
                                                            "label": "显示月份标签"
                                                        }
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
                                {"component": "VExpansionPanelTitle", "text": "CPU/内存设置"},
                                {
                                    "component": "VExpansionPanelText",
                                    "content": [
                                        {
                                            "component": "VRow",
                                            "content": [
                                                {
                                                    "component": "VCol",
                                                    "props": {"cols": 12, "md": 4},
                                                    "content": [{
                                                        "component": "VSelect",
                                                        "props": {
                                                            "model": "performance_size",
                                                            "label": "性能组件宽度",
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
                                                    "props": {"cols": 12, "md": 4},
                                                    "content": [{
                                                        "component": "VTextField",
                                                        "props": {
                                                            "model": "performance_height",
                                                            "label": "性能图高度（120-320）",
                                                            "type": "number",
                                                            "min": 120,
                                                            "max": 320,
                                                            "placeholder": "190"
                                                        }
                                                    }]
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }], {
            "enabled": self._enabled,
            "refresh": self._refresh,
            "show_summary": self._show_summary,
            "color_theme": self._color_theme,
            "show_month_labels": self._show_month_labels,
            "dashboard_size": self._calendar_size,
            "calendar_size": self._calendar_size,
            "performance_size": self._performance_size,
            "cell_scale": self._cell_scale,
            "range": self._range,
            "performance_height": self._performance_height,
        }

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "div",
                "props": {"class": "text-center"},
                "text": "请在仪表板中添加“媒体入库日历图”或“媒体入库性能”组件查看数据。",
            }
        ]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [
            {"key": "calendar", "name": "媒体入库日历图"},
            {"key": "performance", "name": "主机性能"},
        ]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        if key and key not in {"calendar", "performance"}:
            return None

        key = key or "calendar"
        cols = {"cols": 12}
        attrs = {"refresh": self._refresh, "title": "媒体入库组件", "border": True}

        try:
            if key == "performance":
                cols = self._SIZE_COLS.get(self._performance_size, self._SIZE_COLS["half"])
                attrs = {
                    "refresh": self._refresh,
                    "title": "主机性能",
                    "border": True
                }
                perf_data = self.__load_performance_data()
                elements = self.__build_performance_elements(perf_data)
            else:
                cols = self._SIZE_COLS.get(self._calendar_size, self._SIZE_COLS["two_third"])
                attrs = {
                    "refresh": self._refresh,
                    "title": "媒体入库日历图",
                    "border": True
                }
                days = self._RANGE_DAYS.get(self._range, 365)
                grid_data = self.__build_calendar_grid(days=days)
                elements = self.__build_calendar_elements(grid_data)
            return cols, attrs, elements
        except Exception as err:
            return cols, attrs, [
                {
                    "component": "VAlert",
                    "props": {"type": "warning", "variant": "tonal", "density": "compact"},
                    "text": f"媒体入库组件数据加载失败：{str(err)}",
                }
            ]

    def stop_service(self):
        pass

    @staticmethod
    def __safe_refresh(raw_value: Any) -> int:
        try:
            value = int(raw_value)
            return value if value >= 30 else 30
        except Exception:
            return 300

    @staticmethod
    def __safe_scale(raw_value: Any) -> int:
        try:
            value = int(raw_value)
            if value < 80:
                return 80
            if value > 130:
                return 130
            return value
        except Exception:
            return 100

    @staticmethod
    def __safe_perf_height(raw_value: Any) -> int:
        try:
            value = int(raw_value)
            if value < 120:
                return 120
            if value > 320:
                return 320
            return value
        except Exception:
            return 190

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
                    cell = {
                        "date": day_key,
                        "count": day_count,
                        "level": level,
                        "in_range": True,
                        "tooltip": f"{day_key}: {day_count}",
                    }
                    if self._show_month_labels and current_day.day == 1 and week_index not in month_labels:
                        month_labels[week_index] = self._MONTH_ABBR[current_day.month - 1]
                else:
                    cell = {
                        "date": None,
                        "count": 0,
                        "level": 0,
                        "in_range": False,
                        "tooltip": "",
                    }

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
        memory_usage = max(0, min(100, int(memory_usage)))
        return {
            "cpu": round(cpu, 1),
            "memory": memory_usage,
        }

    def __build_calendar_elements(self, grid_data: Dict[str, Any]) -> List[dict]:
        theme_colors = self._COLOR_THEMES.get(self._color_theme, self._COLOR_THEMES["mp_purple"])
        weeks = grid_data["weeks"]
        week_count = grid_data["week_count"]
        month_labels = grid_data["month_labels"]

        scale_ratio = self._cell_scale / 100
        cell_size = max(10, int(round(13 * scale_ratio)))
        cell_gap = max(2, int(round(2 * scale_ratio)))
        row_gap = max(1, int(round(1 * scale_ratio)))
        weekday_col_width = max(18, int(round(20 * scale_ratio)))
        calendar_width = week_count * (cell_size + cell_gap)

        label_cells = []
        if self._show_month_labels:
            for week_index in range(week_count):
                label_cells.append({
                    "component": "div",
                    "props": {
                        "style": {
                            "width": f"{cell_size}px",
                            "minWidth": f"{cell_size}px",
                            "height": "14px",
                            "fontSize": "10px",
                            "lineHeight": "14px",
                            "color": "rgba(var(--v-theme-on-surface), 0.65)",
                            "marginRight": f"{cell_gap}px",
                            "overflow": "visible",
                            "whiteSpace": "nowrap",
                        }
                    },
                    "text": month_labels.get(week_index, ""),
                })

        weekday_texts = ["一", "", "三", "", "五", "", ""]
        weekday_label_elements = []
        day_row_elements = []
        for weekday in range(7):
            row_cells = []
            for week_index in range(week_count):
                cell = weeks[week_index][weekday]
                row_cells.append({
                    "component": "div",
                    "props": {
                        "title": cell["tooltip"] if cell["in_range"] else "",
                        "style": {
                            "width": f"{cell_size}px",
                            "minWidth": f"{cell_size}px",
                            "height": f"{cell_size}px",
                            "borderRadius": "2px",
                            "backgroundColor": theme_colors[cell["level"]],
                            "marginRight": f"{cell_gap}px",
                            "opacity": 1 if cell["in_range"] else 0,
                            "cursor": "default",
                        },
                    },
                })

            weekday_label_elements.append({
                "component": "div",
                "props": {
                    "style": {
                        "width": f"{weekday_col_width}px",
                        "minWidth": f"{weekday_col_width}px",
                        "height": f"{cell_size}px",
                        "lineHeight": f"{cell_size}px",
                        "marginBottom": f"{row_gap}px",
                        "fontSize": "10px",
                        "textAlign": "right",
                        "paddingRight": "4px",
                        "color": "rgba(var(--v-theme-on-surface), 0.65)",
                    }
                },
                "text": weekday_texts[weekday],
            })

            day_row_elements.append({
                "component": "div",
                "props": {
                    "class": "d-flex align-center",
                    "style": {"marginBottom": f"{row_gap}px"},
                },
                "content": row_cells,
            })

        legend = {
            "component": "div",
            "props": {
                "class": "d-flex align-center justify-end",
                "style": {
                    "marginTop": "2px",
                    "gap": "4px",
                    "fontSize": "11px",
                    "color": "rgba(var(--v-theme-on-surface), 0.65)",
                },
            },
            "content": [
                {"component": "span", "text": "少"},
                *[
                    {
                        "component": "div",
                        "props": {
                            "style": {
                                "width": f"{cell_size}px",
                                "height": f"{cell_size}px",
                                "borderRadius": "2px",
                                "backgroundColor": theme_colors[level],
                            }
                        },
                    }
                    for level in range(5)
                ],
                {"component": "span", "text": "多"},
            ],
        }

        stats_row = {
            "component": "VRow",
            "props": {
                "class": "mt-0",
                "noGutters": True,
                "style": {"marginTop": "2px", "marginBottom": "0"},
            },
            "content": [
                {
                    "component": "VCol",
                    "props": {"cols": 12, "md": 3},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "总入库量"},
                        {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["total_count"])},
                    ],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 12, "md": 3},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "活跃天数"},
                        {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["active_days"])},
                    ],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 12, "md": 3},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "峰值单日"},
                        {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["max_count"])},
                    ],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 12, "md": 3},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "统计区间"},
                        {"component": "div", "props": {"class": "text-body-2"}, "text": grid_data["date_range"]},
                    ],
                },
            ],
        }

        main_calendar = {
            "component": "div",
            "props": {"style": {"overflowX": "auto"}},
            "content": [
                {
                    "component": "div",
                    "props": {"style": {"minWidth": f"{calendar_width + weekday_col_width + 8}px"}},
                    "content": [
                        {
                            "component": "div",
                            "props": {
                                "class": "d-flex align-center",
                                "style": {"marginBottom": "1px"},
                            },
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"style": {"width": f"{weekday_col_width}px", "minWidth": f"{weekday_col_width}px"}},
                                },
                                {
                                    "component": "div",
                                    "props": {"class": "d-flex align-center"},
                                    "content": label_cells,
                                },
                            ],
                        } if self._show_month_labels else {"component": "div"},
                        {
                            "component": "div",
                            "props": {"class": "d-flex"},
                            "content": [
                                {"component": "div", "content": weekday_label_elements},
                                {"component": "div", "content": day_row_elements},
                            ],
                        },
                        legend,
                    ],
                }
            ],
        }

        elements: List[dict] = [main_calendar]
        if self._show_summary:
            elements.append(stats_row)

        if grid_data["total_count"] == 0:
            elements.append({
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "density": "compact",
                    "class": "mt-1",
                },
                "text": "当前统计区间暂无入库数据",
            })

        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": elements,
                    }
                ],
            }
        ]

    def __build_performance_elements(self, perf_data: Dict[str, Any]) -> List[dict]:
        perf_chart = {
            "component": "VApexChart",
            "props": {
                "height": self._performance_height,
                "options": {
                    "chart": {
                        "type": "line",
                        "toolbar": {"show": False},
                        "sparkline": {"enabled": False},
                    },
                    "stroke": {
                        "curve": "smooth",
                        "width": [3, 3],
                    },
                    "xaxis": {"categories": ["当前"]},
                    "yaxis": [
                        {"min": 0, "max": 100, "title": {"text": "CPU %"}},
                        {"opposite": True, "min": 0, "max": 100, "title": {"text": "内存 %"}},
                    ],
                    "colors": ["#9155FD", "#16B1FF"],
                    "legend": {"position": "top"},
                    "dataLabels": {"enabled": True},
                    "tooltip": {"shared": True, "intersect": False},
                },
                "series": [
                    {"name": "CPU", "data": [perf_data["cpu"]]},
                    {"name": "内存", "data": [perf_data["memory"]]},
                ],
            },
        }

        summary = {
            "component": "VRow",
            "props": {"class": "mt-1", "noGutters": True},
            "content": [
                {
                    "component": "VCol",
                    "props": {"cols": 6},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "CPU"},
                        {"component": "div", "props": {"class": "text-h6"}, "text": f"{perf_data['cpu']}%"},
                    ],
                },
                {
                    "component": "VCol",
                    "props": {"cols": 6},
                    "content": [
                        {"component": "div", "props": {"class": "text-caption"}, "text": "内存"},
                        {"component": "div", "props": {"class": "text-h6"}, "text": f"{perf_data['memory']}%"},
                    ],
                },
            ],
        }

        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [perf_chart, summary],
                    }
                ],
            }
        ]
