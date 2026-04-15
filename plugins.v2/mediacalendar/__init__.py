import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.db.transferhistory_oper import TransferHistoryOper
from app.plugins import _PluginBase


class MediaCalendar(_PluginBase):
    # 插件名称
    plugin_name = "媒体入库日历图"
    # 插件描述
    plugin_desc = "以贡献日历风格展示最近365天入库数量。"
    # 插件图标
    plugin_icon = "statistic.png"
    # 插件版本
    plugin_version = "1.0.3"
    # 插件作者
    plugin_author = "jonysun"
    # 作者主页
    author_url = "https://github.com/jonysun"
    # 插件配置项ID前缀
    plugin_config_prefix = "mediacalendar_"
    # 加载顺序
    plugin_order = 99
    # 可使用的用户级别
    auth_level = 1

    _enabled: bool = True
    _refresh: int = 300
    _show_summary: bool = True
    _color_theme: str = "github_green"
    _show_month_labels: bool = True
    _dashboard_size: str = "half"

    _MONTH_ABBR: List[str] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
    ]

    _COLOR_THEMES: Dict[str, List[str]] = {
        "github_green": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "high_contrast_green": ["#e5e7eb", "#86efac", "#22c55e", "#16a34a", "#166534"],
        "mp_purple": ["#efebfb", "#d4c4f8", "#b79bf3", "#9c73ee", "#9155FD"]
    }

    def init_plugin(self, config: dict = None):
        config = config or {}
        enabled_value = config.get("enabled")
        if enabled_value is None:
            enabled_value = config.get("enable", True)
        self._enabled = self.__to_bool(enabled_value, default=True)
        self._refresh = self.__safe_refresh(config.get("refresh", 300))
        self._show_summary = self.__to_bool(config.get("show_summary", True), default=True)
        self._color_theme = config.get("color_theme", "github_green")
        if self._color_theme not in self._COLOR_THEMES:
            self._color_theme = "github_green"
        self._show_month_labels = self.__to_bool(config.get("show_month_labels", True), default=True)
        self._dashboard_size = config.get("dashboard_size", "half")
        if self._dashboard_size not in {"half", "three_quarter", "full"}:
            self._dashboard_size = "half"

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "show_summary",
                                            "label": "显示摘要信息"
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "show_month_labels",
                                            "label": "显示月份标签"
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
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
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "color_theme",
                                            "label": "颜色主题",
                                            "items": [
                                                {
                                                    "title": "GitHub Green",
                                                    "value": "github_green"
                                                },
                                                {
                                                    "title": "High Contrast Green",
                                                    "value": "high_contrast_green"
                                                },
                                                {
                                                    "title": "MoviePilot Purple",
                                                    "value": "mp_purple"
                                                }
                                            ]
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "dashboard_size",
                                            "label": "组件宽度",
                                            "items": [
                                                {
                                                    "title": "半宽（类似CPU/内存/网络）",
                                                    "value": "half"
                                                },
                                                {
                                                    "title": "3/4宽（75%）",
                                                    "value": "three_quarter"
                                                },
                                                {
                                                    "title": "全宽（铺满）",
                                                    "value": "full"
                                                }
                                            ]
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": self._enabled,
            "refresh": self._refresh,
            "show_summary": self._show_summary,
            "color_theme": self._color_theme,
            "show_month_labels": self._show_month_labels,
            "dashboard_size": self._dashboard_size
        }

    def get_page(self) -> List[dict]:
        return [
            {
                "component": "div",
                "props": {
                    "class": "text-center"
                },
                "text": "请在仪表板中添加“入库日历图”组件查看数据。"
            }
        ]

    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [{
            "key": "calendar",
            "name": "媒体入库日历图"
        }]

    def get_dashboard(self, key: str = None, **kwargs) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], List[dict]]]:
        if key and key != "calendar":
            return None

        if self._dashboard_size == "half":
            cols = {"cols": 12, "md": 6}
        elif self._dashboard_size == "three_quarter":
            cols = {"cols": 12, "md": 9}
        else:
            cols = {"cols": 12}
        attrs = {
            "refresh": self._refresh,
            "title": "媒体入库日历图",
            "subtitle": "最近365天",
            "border": True
        }

        try:
            grid_data = self.__build_calendar_grid(days=365)
            elements = self.__build_dashboard_elements(grid_data)
            return cols, attrs, elements
        except Exception as err:
            return cols, attrs, [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "warning",
                        "variant": "tonal",
                        "density": "compact"
                    },
                    "text": f"入库日历图数据加载失败：{str(err)}"
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

    def __build_calendar_grid(self, days: int = 365) -> Dict[str, Any]:
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
                        "tooltip": f"{day_key}: {day_count}"
                    }
                    if self._show_month_labels and current_day.day == 1 and week_index not in month_labels:
                        month_labels[week_index] = self._MONTH_ABBR[current_day.month - 1]
                else:
                    cell = {
                        "date": None,
                        "count": 0,
                        "level": 0,
                        "in_range": False,
                        "tooltip": ""
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
            "date_range": f"{start_date.isoformat()} ~ {end_date.isoformat()}"
        }

    @staticmethod
    def __count_to_level(count: int, max_count: int) -> int:
        if count <= 0 or max_count <= 0:
            return 0
        return max(1, min(4, math.ceil((count / max_count) * 4)))

    @staticmethod
    def __load_daily_counts(days: int = 365) -> Dict[str, int]:
        today = date.today()
        first_day = today - timedelta(days=days - 1)
        result = {
            (first_day + timedelta(days=delta)).isoformat(): 0
            for delta in range(days)
        }

        rows = TransferHistoryOper().statistic(days=days)
        for item in rows:
            if not item or len(item) < 2:
                continue
            day_key = str(item[0])
            if day_key in result:
                result[day_key] = int(item[1])
        return result

    def __build_dashboard_elements(self, grid_data: Dict[str, Any]) -> List[dict]:
        theme_colors = self._COLOR_THEMES.get(self._color_theme, self._COLOR_THEMES["github_green"])
        weeks = grid_data["weeks"]
        week_count = grid_data["week_count"]
        month_labels = grid_data["month_labels"]

        cell_size = 10
        cell_gap = 2
        row_gap = 1
        weekday_col_width = 18
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
                            "whiteSpace": "nowrap"
                        }
                    },
                    "text": month_labels.get(week_index, "")
                })

        # GitHub 风格周标：仅显示周一/周三/周五
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
                            "cursor": "default"
                        }
                    }
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
                        "color": "rgba(var(--v-theme-on-surface), 0.65)"
                    }
                },
                "text": weekday_texts[weekday]
            })

            day_row_elements.append({
                "component": "div",
                "props": {
                    "class": "d-flex align-center",
                    "style": {
                        "marginBottom": f"{row_gap}px"
                    }
                },
                "content": row_cells
            })

        legend = {
            "component": "div",
            "props": {
                "class": "d-flex align-center justify-end",
                "style": {
                    "marginTop": "4px",
                    "gap": "4px",
                    "fontSize": "11px",
                    "color": "rgba(var(--v-theme-on-surface), 0.65)"
                }
            },
            "content": [
                {
                    "component": "span",
                    "text": "少"
                },
                *[
                    {
                        "component": "div",
                        "props": {
                            "style": {
                                "width": f"{cell_size}px",
                                "height": f"{cell_size}px",
                                "borderRadius": "2px",
                                "backgroundColor": theme_colors[level]
                            }
                        }
                    }
                    for level in range(5)
                ],
                {
                    "component": "span",
                    "text": "多"
                }
            ]
        }

        summary_items = []
        if self._show_summary:
            summary_items = [
                {
                    "component": "VRow",
                    "props": {
                        "class": "mt-1",
                        "noGutters": True
                    },
                    "content": [
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {"component": "div", "props": {"class": "text-caption"}, "text": "总入库量"},
                                {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["total_count"])}
                            ]
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {"component": "div", "props": {"class": "text-caption"}, "text": "活跃天数"},
                                {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["active_days"])}
                            ]
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "md": 4},
                            "content": [
                                {"component": "div", "props": {"class": "text-caption"}, "text": "峰值单日"},
                                {"component": "div", "props": {"class": "text-h6"}, "text": str(grid_data["max_count"])}
                            ]
                        }
                    ]
                },
                {
                    "component": "div",
                    "props": {
                        "class": "text-caption",
                        "style": {
                            "marginTop": "2px",
                            "color": "rgba(var(--v-theme-on-surface), 0.65)"
                        }
                    },
                    "text": grid_data["date_range"]
                }
            ]

        if grid_data["total_count"] == 0:
            summary_items.append({
                "component": "VAlert",
                "props": {
                    "type": "info",
                    "variant": "tonal",
                    "density": "compact",
                    "class": "mt-1"
                },
                "text": "最近365天暂无入库数据"
            })

        card_content = [
            {
                "component": "div",
                "props": {
                    "style": {
                        "overflowX": "auto"
                    }
                },
                "content": [
                    {
                        "component": "div",
                        "props": {
                            "style": {
                                "minWidth": f"{calendar_width + weekday_col_width + 8}px"
                            }
                        },
                        "content": [
                            {
                                "component": "div",
                                "props": {
                                    "class": "d-flex align-center",
                                    "style": {
                                        "marginBottom": "2px"
                                    }
                                },
                                "content": [
                                    {
                                        "component": "div",
                                        "props": {
                                            "style": {
                                                "width": f"{weekday_col_width}px",
                                                "minWidth": f"{weekday_col_width}px"
                                            }
                                        }
                                    },
                                    {
                                        "component": "div",
                                        "props": {
                                            "class": "d-flex align-center"
                                        },
                                        "content": label_cells
                                    }
                                ]
                            } if self._show_month_labels else {
                                "component": "div"
                            },
                            {
                                "component": "div",
                                "props": {
                                    "class": "d-flex"
                                },
                                "content": [
                                    {
                                        "component": "div",
                                        "content": weekday_label_elements
                                    },
                                    {
                                        "component": "div",
                                        "content": day_row_elements
                                    }
                                ]
                            },
                            legend
                        ]
                    }
                ]
            }
        ]

        elements = [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {
                            "cols": 12
                        },
                        "content": card_content
                    }
                ]
            }
        ]

        elements.extend(summary_items)
        return elements
