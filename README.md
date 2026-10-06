# 电网事件驱动仿真与自动投切决策系统

> 一个基于 VeraGrid 的事件驱动电网仿真平台，覆盖从仿真引擎到规则引擎到可视化的完整闭环。
>
> **状态**：全部 6 个 Phase 完成 ✅  
> **作者**：liuka  
> **起始**：2026-10-06

## 项目目标

构建一个**事件驱动的电网仿真平台**，用于研究真实电网在动态扰动下的运行行为，并支撑自动投切策略的离线生成与在线验证。

1. **稳态运行**：模拟真实电网拓扑 + 负荷/电源时序
2. **动态扰动**：负荷新增/退出、发电机跳机、线路故障等事件注入
3. **自动投切**：根据电网状态自动生成开关/切负荷/调出力等动作
4. **实时观测**：拓扑、节点电压、支路载流、发电机出力、损耗等状态时间序列
5. **规则生成**：从大量仿真数据中归纳出保护/重构规则

## 项目结构

```
.
├── docs/
│   └── DESIGN.md                      ← 完整设计文档（370+ 行）
├── lab_scripts/                       ← 仿真核心 + 8 个实验 demo
│   ├── event_sim.py                   ← Phase 1: 事件注入器 + 仿真器
│   ├── radial_feeder.py               ← Phase 2: 5-bus 辐射状配电 feeder
│   ├── rule_engine.py                 ← Phase 3: 4 条保护规则 + 引擎
│   ├── load_profiles.py               ← Phase B: ZIP/闪变/启停模型
│   ├── rule_generator.py              ← Phase 4: 候选枚举 + 评分搜索
│   ├── dashboard.py                   ← Phase 5: Plotly 仪表盘构建器
│   ├── exp01_power_flow_ieee14.py     ← 实验一：基础潮流
│   ├── exp02_short_circuit_ieee14.py  ← 实验二：短路电流
│   ├── exp03_event_driven_sim.py      ← 实验三：事件注入验证
│   ├── exp04_rule_engine.py           ← 实验四：规则引擎 v1
│   ├── exp05_reconfigure.py           ← 实验五：配电自动重构
│   ├── exp06_realistic_loads.py       ← 实验六：真实负荷扰动
│   ├── exp07_rule_generation.py       ← 实验七：规则生成
│   ├── exp08_dashboard.py             ← 实验八：实时仪表盘
│   ├── exp07_results*.csv             ← 规则评分结果
│   ├── exp0X_*.png                    ← 各实验可视化
│   └── exp08_dashboard.html           ← 单文件交互式仪表盘
├── Grids_and_profiles/grids/          ← IEEE / Kundur 测试系统
├── gridcal_install.log                ← VeraGrid 安装日志
├── veragrid_install.log
├── veragrid_test.py
├── veragrid_jupyter_demo.ipynb        ← 早期 demo notebook
├── start-*.cmd                        ← 启动脚本
└── .gitignore
```

## 6 个 Phase 速览

| Phase | 主题 | 关键产出 |
|---|---|---|
| **1** | 事件驱动仿真 | `event_sim.py` + exp03 — IEEE 14 注入 5 个事件，91 步全收敛 |
| **2** | 拓扑可控建模 | `radial_feeder.py` + exp05 — F1B 失电从 25 步降到 1 步（R004 自动重构） |
| **3** | 规则引擎 v1 | `rule_engine.py` + exp04 — 4 条规则改善系统指标（最低电压 +0.010 pu，最大载流 -15%） |
| **B** | 真实负荷扰动 | `load_profiles.py` + exp06 — ZIP 折算 + 闪变 + 启停概率模型 |
| **4** | 规则生成 | `rule_generator.py` + exp07 — 枚举 ~30 条候选规则 + 双场景评分对比 |
| **5** | 实时可视化 | `dashboard.py` + exp08 — 单文件 HTML 仪表盘（拓扑动画 + 时序曲线 + 指标卡片） |

详细设计、踩坑记录、验证结果见 [`docs/DESIGN.md`](docs/DESIGN.md)。

## 快速开始

```bash
# 激活环境
gridcal-env\Scripts\activate

# 运行单个实验
python lab_scripts/exp03_event_driven_sim.py

# 生成最新仪表盘
python lab_scripts/exp08_dashboard.py
# 浏览器打开 lab_scripts/exp08_dashboard.html
```

## 关键技术决策

- **VeraGrid 作仿真后端**（潮流/动态/短路），自定义事件+规则层
- **Line + active 标志**而非 Switch 类（带阻抗 + 可投切，更灵活）
- **规则冷却机制**防止低电压 → 切负荷 → 电压恢复 → 又触发的循环
- **Simulator 规则触发后立即 re-PF**（零延迟优化，消除 1 步 blackout）
- **Plotly 单文件 HTML**仪表盘（CDN 引入，无服务器）

## 已修过的坑（API 踩坑记录）

- `pf.Sbus` / `pf.Sf` 是 **MW**（不是 pu，尽管名字像 pu）
- `pf.loading` 字段对未通流支路返回垃圾值（1.58e16%）
- VeraGrid 默认 `ln.rate = 1.0`（基本无意义），必须显式设置
- `Bus.is_slack` 属性存在（不是 `is_reference`）
- Windows GBK 终端不支持 ✓ ✗ 等 unicode
- `load_counter` 全局变量跨场景需要重置

## 后续可扩展方向

- 真·实时仪表盘（Dash + WebSocket）
- 规则库 YAML/JSON 化（脱离代码硬编码）
- 拓扑坐标自动推断（不再硬编码 IEEE 14）
- R004 加故障隔离逻辑（先打开分段开关再合 TIE）
- tie_map 自动拓扑识别
- 与 SCADA 真实数据接入
- 概率潮流 (PPF) / 蒙特卡洛场景库
- RL 智能体在仿真环境训练
