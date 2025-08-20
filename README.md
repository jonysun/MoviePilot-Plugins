# MoviePilot-Plugins
MoviePilot官方插件市场：https://github.com/jxxghp/MoviePilot-Plugins

# 站点刷流（低频加强版）
## 改进：
自定义站点配置参数强化：

- 支持站点保种体积 site_size:int    单位:gb 使用方法等同size

- 支持下载人数     peer:2-20        单位：人 使用方法等同seeder

- 种子删除通知增加分享率信息

## todo
- [ ] RSS流url

- [ ] 根据站点分享率动态分配site_size:int 和顺序 sequential

- [ ] 同步官方插件commit
      
- [X] 单个站点配置刷流顺序优先级。sequential: int

- [X] 增加仪表盘，对站点按时间汇总上传、下载量、分享率。

- [ ] 定时通知站点刷流信息汇总

## 参考
修改自原作者InfinityPacer 插件

https://github.com/InfinityPacer/MoviePilot-Plugins

# 转移做种（修改版）
## 改进
修改标签的逻辑关系为满足任意标签，使用英文逗号分隔。原插件逻辑为同时满足所有标签。

增加一个逻辑开关于配置页底下。

## todo
- [ ] 联动辅种插件，转移即辅种

## 参考
修改自原作者jxxghp插件1.10.2

https://github.com/jxxghp/MoviePilot-Plugins/tree/main/plugins.v2/torrenttransfer

# 刷流种子整理（自用修改版）
修改自原作者InfinityPacer 插件

- 增加对“站点刷流（低频加强版）”的支持
  
