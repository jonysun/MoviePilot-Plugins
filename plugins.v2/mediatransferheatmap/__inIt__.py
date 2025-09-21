import base64
import json
import random
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional, Union, Set
from urllib.parse import urlparse, parse_qs, unquote, parse_qsl, urlencode, urlunparse

import pytz
from app.helper.sites import SitesHelper
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import schemas
from app.chain.torrents import TorrentsChain
from app.core.config import settings
from app.core.context import MediaInfo
from app.core.metainfo import MetaInfo
from app.db.site_oper import SiteOper
from app.db.subscribe_oper import SubscribeOper
from app.helper.downloader import DownloaderHelper
from app.log import logger
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission
from app.plugins import _PluginBase
from app.schemas import NotificationType, TorrentInfo, MediaType, ServiceInfo
from app.schemas.types import EventType
from app.utils.http import RequestUtils
from app.utils.string import StringUtils


class MediaTransferHeatmap(_PluginBase):
    # 插件基本信息 (根据你的实际情况修改)
    plugin_name = "媒体整理热力图"
    plugin_desc = "在仪表盘显示媒体文件整理活动的日历热力图。"
    plugin_icon = "brush.jpg" # 使用合适的图标
    plugin_version = "1.0.1"
    plugin_author = "jonysun"
    author_url = "https://github.com/jonysun"
    plugin_config_prefix = "mediatransferheatmap_"
    plugin_order = 25
    auth_level = 1


    def get_api(self) -> List[Dict[str, Any]]:
        """
        注册插件 API
        """
        return [
            {
                "path": "/data/heatmap",              # 前端将调用 plugin/MediaTransferHeatmap/data/heatmap
                "endpoint": self._get_heatmap_data_api, # 指向处理请求的方法
                "methods": ["GET"],                   # HTTP 方法
                "auth": "bear",                       # 认证类型，必须是 "bear"
                "summary": "获取日历热力图数据"         # 描述
            }
        ]

    def _get_heatmap_data_api(self, request) -> dict: # request 类型取决于 MoviePilot 具体实现
        """
        API 端点：获取热力图数据
        """
        # 从请求中获取参数 (如果需要)
        # params = getattr(request, 'query_params', {}) # FastAPI 风格
        # months = int(params.get("months", 3)) if params.get("months") else 3
        months = 3 # 简化处理，固定为3个月

        heatmap_data = self._get_heatmap_data_last_n_months(months) # 调用数据获取方法
        return {"success": True, "data": heatmap_data}

    def _get_heatmap_data_last_n_months(self, months: int = 3) -> List[Dict[str, Any]]:
        """
        获取最近完整 N 个月的整理统计数据。
        返回: [{"date": "YYYY-MM-DD", "count": N}, ...]
        """
        # --- 这部分代码与之前讨论的完全一致 ---
        from datetime import datetime, timedelta
        # from dateutil.relativedelta import relativedelta # 确保已导入

        today = datetime.today()
        start_date = (today - relativedelta(months=months-1)).replace(day=1)

        if today.month == 12:
            end_date = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

        logger.debug(f"[MediaTransferHeatmap] 计算热力图数据范围: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

        days_to_query = (end_date - start_date).days + 1

        db_gen = get_db()
        db = next(db_gen)
        try:
            raw_stats = TransferHistory.statistic(db, days=days_to_query)
            stats_dict = {date_str: count for date_str, count in raw_stats}

            calendar_data = []
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime('%Y-%m-%d')
                count = stats_dict.get(date_str, 0)
                calendar_data.append({"date": date_str, "count": count})
                current_date += timedelta(days=1)

            return calendar_data

        except Exception as e:
            logger.error(f"[MediaTransferHeatmap] 获取日历热力图数据失败: {e}")
            return []
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
        # --- 结束一致代码 ---

    def get_render_mode(self) -> Tuple[str, str]:
        """
        获取插件渲染模式
        """
        # 使用 vue 模式，并指定前端构建产物的目录
        return "vue", "dist/assets" # 确保这与你前端构建输出目录和部署目录匹配

    def get_dashboard(self, key: str, **kwargs) -> Tuple[Dict[str, Any], Dict[str, Any], List[dict]]:
        """
        获取插件仪表盘页面 (使用模块联邦后，这部分通常返回空或简单结构)
        """
        cols = {"cols": 12}
        attrs = {} # {"refresh": 3600} 如果需要
        # 关键：返回空列表，让 Module Federation 的 Dashboard.vue 组件来渲染
        elements = []
        return cols, attrs, elements


