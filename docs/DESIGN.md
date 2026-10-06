# 电网事件驱动仿真与自动投切决策系统 — 设计文档

> 维护者：liuka  
> 起始：2026-10-06  
> 状态：**全部 6 个 Phase 完成 ✅**

---

## 1. 项目目标

构建一个**事件驱动的电网仿真平台**，用于研究真实电网在以下场景下的运行行为，并支撑自动投切策略的离线生成与在线验证：

1. **稳态运行**：模拟真实电网拓扑 + 负荷/电源时序
2. **动态扰动**：负荷新增/退出、发电机跳机、线路故障等事件注入
3. **自动投切**：根据电网状态自动生成开关/切负荷/调出力等动作
4. **实时观测**：拓扑、节点电压、支路载流、发电机出力、损耗等状态的时间序列
5. **规则生成（远期）**：从大量仿真数据中归纳出保护/重构规则

### 已确定的关键决策

| 维度 | 决策 | 理由 |
|---|---|---|
| 实时性 | 事件级秒级响应 | 不需要 wall-clock 实时，仿真可加速跑 |
| 决策算法 | 离线枚举 + 仿真评估 | 可解释、易调优、便于发表 |
| 起步规模 | IEEE 14 母线 | 已有数据、计算快、便于迭代 |
| 起步路径 | Phase 1（事件注入）→ 3（规则）→ 2（开关）→ 4（生成）→ 5（可视化） | 先验证决策逻辑，再补物理执行能力 |

---

## 2. 系统架构

### 2.1 四层闭环

```
  ┌──────────┐    事件    ┌──────────────┐   状态向量  ┌────────────┐
  │  事件注入 │ ────────▶ │   VeraGrid   │ ──────────▶ │  状态观测器 │
  │ (负载/故障│           │  仿真引擎    │            │ (电压/载流/│
  │  /发电机) │           │ (潮流/动态)  │            │  频率/拓扑) │
  └──────────┘            └──────┬───────┘            └─────┬──────┘
       ▲                         │                          │
       │  拓扑修改               │  SCADA/EMS 遥测          ▼
       │                    ┌────▼─────────────────────────────┐
       │                    │       规则引擎 / 决策层          │
       │                    │  • 规则库（IF-THEN / 保护逻辑） │
       │                    │  • 网络重构优化（MILP/启发式）  │
       │                    │  • RL 智能体                   │
       │                    └────┬─────────────────────────────┘
       │                         │ 开关/切负荷/调出力动作
       └─────────────────────────┘
```

### 2.2 子系统职责

| 子系统 | 职责 | 当前实现 |
|---|---|---|
| ① 事件注入器 | 按时序注入"负荷新增/退出、发电机跳机、线路跳闸、开关变位" | ✅ `event_sim.inject()` |
| ② 仿真引擎 | VeraGrid（潮流/动态/短路） | ✅ 已对接 |
| ③ 状态观测器 | 拓扑、节点电压、支路载流、发电机出力、损耗、开关状态快照 | ✅ `event_sim.snapshot()` |
| ④ 规则引擎 | 监测→决策→动作（4 条规则） | ✅ Phase 3 完成 |
| ⑤ 负荷时序 | ZIP / 闪烁 / 启停概率 | ✅ Phase B 完成 |

---

## 3. 阶段路线

### Phase 1 — 事件驱动仿真 ✅ 完成

- ✅ Event 数据结构（6 种事件类型：load_add/drop, gen_trip/commit, line_trip/close）
- ✅ grid mutation 注入接口（基于 VeraGrid `.active` 标志）
- ✅ 状态快照函数（DataFrame 宽表）
- ✅ 主仿真循环 Simulator.run()
- ✅ IEEE 14 验证（5 事件剧本，91 步全收敛）

**交付物**：`lab_scripts/event_sim.py` + `lab_scripts/exp03_event_driven_sim.py`

### Phase 2 — 拓扑可控建模 ✅ 完成

- ✅ 用 Line.active=True/False 表达"开关"语义（带阻抗 + 可投切，比 Switch 类更灵活）
- ✅ 构建 5-bus 双馈线辐射状测试系统（radial_feeder.py）：SRC → S01/S02 → F1A/F2A → S13/S24 → F1B/F2B，TIE 常开
- ✅ R004_RECONFIGURE 自动重构规则：检测带载母线 V<0.05pu → 闭合 tie 开关转供
- ✅ exp05 demo 验证：F1B 失电时长从 25 步 → 1 步

**交付物**：
```
lab_scripts/
├── radial_feeder.py                ← 5-bus 双馈线 + 联络 feeder 构造器
├── exp05_reconfigure.py            ← Phase 2 验证 demo
└── exp05_reconfigure.png           ← 对比可视化
docs/DESIGN.md                       ← 已更新 Phase 2 验证结果
```

**关键技术决策**：
- 用 Line + active 标志 而不是 Switch 类：避免阻抗与可控性分离的复杂性
- snapshot 增加 `sw_<name>` 字段记录开关状态，便于事后可视化真实动作时序
- tie_map 参数化：`build_reconfigure_rule(tie_map={...})` 让规则可适配不同拓扑

**Phase 2 验证结果**

| 场景 | F1B 最低电压 | F1B 失电时长 | TIE 动作 |
|---|---|---|---|
| 无规则 | 0.000 pu（永久失电） | **25 步** | 始终断开 |
| 有 R004 | 0.000 pu（仅 1 步） | **1 步** | t=5 闭合 → t=30 断开 |

**R004 工作机制**：
1. 监测所有带载母线电压
2. 发现 V < 0.05 pu 的母线 → 判定为失电
3. 查 tie_map 找到对应的 tie 开关名
4. 闭合 tie 开关 → 通过备用馈线转供
5. 在 snapshot 中记录 `sw_<name>` 状态便于回放

**已知局限**：
- tie_map 是硬编码映射，未做拓扑推断
- 未考虑潮流约束（闭合 tie 后可能过载）
- 未做故障隔离（如果故障段在 F1A-F1B 之间，闭合 TIE 之前应先打开 S13）

### Phase 3 — 规则引擎 v1 ✅ 完成

- ✅ Rule 数据结构（id / description / when / then / cooldown_s / persistent / fire_count）
- ✅ RuleEngine 调度器（冷却控制、日志记录、错误捕获）
- ✅ 3 条基础规则（执行动作均为切负荷/降出力，不需要开关）：
  - **R001_UVLS**：低压减载 — 任一节点 V < 0.93 pu → 切最差母线 30% 负荷
  - **R002_OVGR**：过压减出力 — 任一非 slack 节点 V > 1.10 pu → 降出力 20%（跳过 P=0 发电机）
  - **R003_OVERLOAD**：重载切负荷 — 任一线路 loading > 130% → 末端母线切 10% 负荷
- ✅ 接入 Simulator 主循环（每步 PF 后评估，动作在下一帧 PF 体现）
- ✅ 对比 demo 验证规则改善系统指标

**交付物**：`lab_scripts/rule_engine.py` + `lab_scripts/exp04_rule_engine.py`

#### Phase 3 验证结果

事件剧本（与 exp03 相同）：+50MW@BUS14 → +30MW@BUS9 → G2跳机 → 线2-4跳闸 → -50MW@BUS14

| 指标 | 无规则 | 有规则 | 改善 |
|---|---|---|---|
| 最低电压 | 0.9174 pu | **0.9274 pu** | +0.010 pu |
| 最大线路载流 | 171.27% | **156.27%** | -15% |
| 最大损耗 | 39.59 MW | **32.60 MW** | -7 MW |

规则触发统计（共 13 次）：
- **R001_UVLS**：1 次（t=25s，BUS 14 电压 0.927 触发，切 15MW）
- **R002_OVGR**：0 次（本场景无过压，无需触发）
- **R003_OVERLOAD**：12 次（t=10~65s，1_2_1 持续过载，分批切 BUS 2 共 ~15MW）

**关键发现**：
- 规则有效降低最坏情况严重度，但无法完全消除过载（IEEE 14 在此剧本下结构性受限）
- 真实系统中需配合拓扑重构（Phase 2 开关）才能彻底解决 N-1 后的热稳定问题
- 冷却机制防止"低电压 → 切 → 电压恢复 → 又触发"的循环

### Phase B — 真实负荷扰动层 ✅ 完成（用户路线图外）

用户提问："工厂负荷实际会不定时开关、变频器等负载非稳态负荷也无规则的周期性电流，在仿真的时候应该怎么展示和处理？"

按推荐路径推进的附加 phase，提供规则生成的逼真训练环境。

- ✅ `LoadProfile` 数据模型（ZIP 系数 + 闪烁幅度/频率 + 启停概率 + 状态）
- ✅ `LoadProfiler` 时序演化引擎（tick → 更新启停/ZIP/闪烁，写入 grid）
- ✅ 集成到 Simulator 主循环（每步 PF 前 tick，PF 后 update_v）
- ✅ 3 个预设模板：`industrial_factory` / `vfd_load` / `residential`
- ✅ exp06 在 IEEE 14 上验证三类特性

**交付物**：
```
lab_scripts/
├── load_profiles.py                 ← LoadProfile + LoadProfiler + 3 模板
├── exp06_realistic_loads.py         ← Phase B 验证 demo
└── exp06_realistic_loads.png        ← 4 子图可视化
```

**关键技术细节**：
- ZIP 折算基于**上一步电压**（避免内层迭代），对秒级仿真足够
- 闪变模型：`P(t) = P_base · (1 + A·sin(2π·f·t)) · zip_factor · state`
- 启停采用**离散时间马尔可夫**：每步 `p(state change) = rate · dt`
- 多个 profile 共用同一母线时，功率合并到第一个负荷（简化处理）

**Phase B 验证结果（exp06）**

事件剧本：t=30s 加工厂@BUS14 + t=60s 加 VFD@BUS9 + t=180s 撤除 + 200s 仿真

| Profile | 模板 | 运行率 | 备注 |
|---|---|---|---|
| 居民@BUS 14 | zip_z=0.6 + 启停 | **58.7%** | 实际出现 1 次 ~15s 停机 |
| 居民@BUS 13 | 同上 | 92.5% | 偶发停机 |
| 工厂@BUS 14 | zip_p=0.5 + 低停机 | 100% | t=30s 加入 |
| 变频器@BUS 9 | zip_p=1.0 + 8Hz 闪烁 | 100% | t=60s 加入 |

**观察**：
- 11 个 profile，201/201 步全部收敛
- 规则引擎**无触发**（v_under=0.95 未被突破，ZIP 折算后系统仍稳）
- BUS 14 居民随机停机引发**轻微电压恢复**（+0.01 pu）
- 闪烁对电压影响小（5% P 波动经网络衰减），主要影响电能质量

### Phase 4 — 规则生成 ✅ 完成

按用户最早路线选择"枚举 + 仿真评估"实现。

- ✅ `RuleSpec` 数据模型（family / threshold / target / action_param）
- ✅ 4 类规则生成器：UVLS / OVGR / OVERLOAD / RECONF
- ✅ `materialize(spec)` 把 RuleSpec 实例化为可执行 Rule
- ✅ `evaluate_rule(spec, scenario)` 跑仿真返回 (score, metrics)
- ✅ `run_search(scenario, specs)` 批量评估并排名
- ✅ `evaluate_compound(specs)` 评估复合规则
- ✅ exp07 在辐射状 feeder 上做两个场景对比

**交付物**：
```
lab_scripts/
├── rule_generator.py                  ← RuleSpec + 候选生成器 + 评分
├── exp07_rule_generation.py           ← 双场景对比 demo
└── exp07_rule_generation.png          ← 4 子图可视化
docs/DESIGN.md                          ← 已更新
```

**关键技术细节**：
- 评分函数：`score = 100·min_v − 0.1·max_load − 2·blackout − 0.01·max_loss − 0.05·shed`
- 候选空间默认 ~30 条规则，可在 exp07 中调整
- **零延迟优化**：simulator 在规则触发后立即 re-PF，消除 1 步延迟（blackout 从 1 步降到 0 步）

**Phase 4 验证结果（exp07 双场景）**

| 场景 | 负荷 | 最佳规则 | Score | min_v | max_load | blackout |
|---|---|---|---|---|---|---|
| A 轻负荷 | 3 MW/馈线 | RECONF_TIE | **85.58** | 0.8706 pu | 14.8% | 0 步 |
| B 高负荷 | 10 MW/馈线 + 12MVA 限额 | RECONF_TIE | **71.18** | 0.8246 pu | 112.4% | 0 步 |

**关键发现**：
1. **RECONF_TIE 在两个场景下都获胜** —— 是该拓扑下"基础必选"规则
2. **复合规则（RECONF+UVLS/OVL）不显著优于 RECONF**：
   - 场景 A：其他规则不触发，无差异
   - 场景 B：UVLS 误触发并过度切负荷，得分反低
3. **OVERLOAD 规则的局限**：触发时刻晚于峰值捕获时刻，无法降低 max_load
4. **评分函数的局限**：取 max_load 峰值，不反映 OVL 后续切负荷的稳态效果

**改进方向**：
- 评分改用"过载时长"或"过载持续时间加权"而非峰值
- 增加**预判类规则**（基于负载预测提前动作）
- 增加**协调型规则**（"先切负荷再闭合 TIE"的事件序列）

### Phase 5 — 实时可视化 ✅ 完成

按推荐路径推进，做单文件 HTML 仪表盘（无服务器，用 Plotly CDN）。

- ✅ `dashboard.py` 提供 4 个核心构建器：
  - `build_topology_figure(grid, snapshot)` 静态拓扑（节点电压/线路载流着色）
  - `build_topology_animation(grid, df)` 拓扑动画（▶ 播放 + 时间滑块）
  - `build_timeseries_figure(df, events)` 4 子图时序曲线（hover 联动）
  - `assemble_dashboard(...)` 拼装单 HTML（已并入 exp08）
- ✅ IEEE 14 母线硬编码坐标（标准 PSS/E 教材布局）
- ✅ 辐射状 feeder 自动用内置坐标
- ✅ 拓扑着色规则：节点 V（绿/橙/红/黑）+ 线路 loading（绿/橙/红）

**交付物**：
```
lab_scripts/
├── dashboard.py                  ← Plotly 图表构建器
├── exp08_dashboard.py            ← 完整仪表盘生成 demo
└── exp08_dashboard.html          ← 单文件 HTML（264 KB，含 CDN Plotly）
docs/DESIGN.md                     ← 已更新
```

**关键技术细节**：
- 拓扑动画用 `go.Frame` + `updatemenus` 按钮 + `sliders`，30 帧抽样
- 时序图用 `make_subplots(4, 1, shared_xaxes=True)`
- hover 模式 `x unified`：同一时间所有曲线值在一个 tooltip
- HTML 用 `<script src="cdn.plot.ly">` 引入 Plotly JS，无需打包
- 拓扑坐标：IEEE 14 用硬编码（教材标准），其它电网用环形退化布局

**Phase 5 验证结果（exp08）**

| 项 | 值 |
|---|---|
| HTML 大小 | 264 KB |
| Plotly.newPlot 调用 | 2（拓扑动画 + 时序曲线） |
| 内嵌图表 | 拓扑动画 + 时序曲线 + 8 卡片 + 2 表格 |
| 仿真步数 | 91 步全收敛 |
| 规则触发 | 13 次 |
| 双语支持 | 中文标题 + CJK 字体 |

**仪表盘包含的组件**：
1. **8 个关键指标卡片**：总步数 / 收敛 / 最低电压 / 最大载流 / 最大损耗 / 失电时长 / 切负荷量 / 规则触发
2. **拓扑动画**：▶ 播放按钮 + 时间滑块，节点按电压着色（绿/橙/红/黑），线路按载流着色
3. **时序曲线**：4 子图（电压/载流/出力/损耗）+ 事件竖线 + hover 联动
4. **事件日志表**：所有触发的事件按时序列出
5. **规则触发日志表**：规则触发时刻 + 动作描述

**打开方式**：
```
# Windows
start lab_scripts/exp08_dashboard.html

# 或浏览器拖入文件
```

**未来可扩展方向**（未实现）：
- 真·实时（每 N 秒自动重跑仿真 + 更新图表）—— 需要 Dash 服务器
- 多场景对比（并列多个仪表盘）
- 拓扑编辑器（手动拖动母线/线路）
- 与 SCADA 真实数据接入

### Phase 5 — 实时可视化

Grafana + InfluxDB / Plotly Dash / 自建 Web。拓扑着色、过载告警、事件时间轴。

---

## 4. 真实负荷建模思路（核心讨论）

### 4.1 现实负荷的分类

| 负荷类型 | 物理特性 | 潮流中表示 | 时间特性 |
|---|---|---|---|
| 异步电机群（工厂主流） | 转差率随电压变化 | ZIP 模型 / 异步电机等值 | 启停冲击 5-7×In |
| 变频器/整流器/电力电子 | 直流侧储能，闭环控制 | 恒功率负荷 (CPL) | μs 级响应 |
| 电弧炉、轧机 | 随机电弧、冲击 | 随机过程 + 谐波电流源 | 0.1-10s 波动 |
| 居民/商业 | 离散设备开关 | 概率模型 + 周期曲线 | 分钟级 |
| 闪变源 (Flicker) | 0.5-25Hz 波动 | 潮流无法直接表示 | 包络 |

### 4.2 建模策略（针对本项目）

**基线（稳态潮流层）**：

- **普通负荷**：ZIP 模型 — `P = a·V² + b·V + c`，三部分系数和为 1
- **变频器负荷**：当 CPL，注意负增量阻抗（恶化电压稳定性）
- **大冲击负荷**：作为**事件**单独注入（已支持 `load_add/drop`）
- **随机性**：概率潮流 (Probabilistic Power Flow) 或蒙特卡洛

**电能质量（独立监测）**：
- 闪变、谐波、间谐波 → 不解入潮流，单独用谐波潮流/频率扫描

**接口设计**（融入 Simulator）：

```python
@dataclass
class LoadProfile:
    base_P: float              # MW 基线
    base_Q: float              # MVar 基线
    zip_z: float = 0.3         # 恒阻抗比例
    zip_i: float = 0.3         # 恒电流比例
    zip_p: float = 0.4         # 恒功率比例
    flicker_amp: float = 0.0   # 闪变幅度 (pu)
    flicker_freq: float = 0.0  # 闪变频率 (Hz)
    switch_on_prob: float = 0.0
    switch_off_prob: float = 0.0
```

每个仿真步长：按 `switch_*_prob` 决定启停，叠加闪变分量，再算潮流。

### 4.3 不会塞进潮流的内容

- 谐波、间谐波 → 谐波潮流 / 频率扫描（VeraGrid 有 `harmonic` 模块）
- μs 级电磁暂态 → EMT 仿真
- 闪变包络 → 仅作为电能质量指标（Pst）单独监测

---

## 5. 当前代码结构

```
C:/code/research/
├── docs/
│   └── DESIGN.md                       ← 本文档
├── lab_scripts/
│   ├── exp01_power_flow_ieee14.py      ← 实验一：基础潮流
│   ├── exp02_short_circuit_ieee14.py   ← 实验二：短路电流
│   ├── event_sim.py                    ← 事件注入器 + 仿真器（Phase 1）
│   └── exp03_event_driven_sim.py       ← Phase 1 验证 demo
├── Grids_and_profiles/grids/           ← 多套 IEEE / Kundur 测试系统
└── veragrid_*.log, *.cmd, *.ipynb      ← 安装与启动产物
```

---

## 6. API 踩坑记录（VeraGrid 6.0.22 实测）

后续再做类似工作直接避坑：

| 坑 | 现象 | 解决办法 |
|---|---|---|
| `pf.Sbus` 单位 | 名字像 pu，实际是 **MW** | 不要 `* Sbase` |
| `pf.Sf` 单位 | 也是 **MW**（与 Sbus 一致） | 直接当 MW 用 |
| `pf.loading` 字段 | 对未通流支路返回 `1.58e16%` 等垃圾值 | 自己用 `|Sf|/rate * 100` 算 |
| Line `.rate` 字段 | IEEE 14 的 .raw 文件不带 rate（=0） | 按电压等级默认：≥110kV→150MVA |
| Slack Pset | 不写入 `gen.P` 字段 | 从 `pf.Sbus[bus_idx].real + local_load` 反推 |
| Windows GBK 终端 | 不能打印 ✓/✗ 等 unicode | 改用 ASCII：`OK / FAIL`、`+ / - / !!` |
| Generator `active` | trip 后 PF 仍收敛，其他机 Pset 不变 | 行为正确（slack 自动吸收），但需在状态读取时正确换算 |

---

## 7. 关键验证结果

### Phase 1 验证（exp03 事件剧本）

事件序列：基线 → +50MW@BUS14 → +30MW@BUS9 → G2跳机 → 线2-4跳闸 → -50MW@BUS14

| 时刻 | 事件 | BUS 14 V | 线 1_2_1 loading | 线 4_5_1 loading | 总损耗 |
|---|---|---|---|---|---|
| 0s | 基线 | 1.036 pu | 105% | 42% | 13.4 MW |
| 10s | +50MW@14 | 0.943 pu | 133% | 46% | 24.7 MW |
| 25s | +30MW@9 | 0.927 pu | 149% | 51% | 30.0 MW |
| 40s | G2 跳机 | 0.923 pu | **171%** ⚠ | 53% | 34.4 MW |
| 55s | 线 2-4 跳闸 | 0.917 pu | 159% | **86%** | 39.6 MW |
| 70s | -50MW@14 | 1.017 pu | 133% | 76% | 23.3 MW |

91/91 步全部收敛（说明 IEEE 14 在此剧本下仍稳定，但 1_2_1 已严重过载 — 真实系统会触发保护）。

### Phase 3 验证（待完成）

将对比 "无规则" vs "有规则" 两组实验，验证 R001/R002/R003 在关键时刻的触发与改善效果。

---

## 8. 下一步

1. **Phase 3 收尾**：完成 rule_engine.py + exp04 demo，跑通"规则改善系统指标"
2. **Phase 2 启动**：在 IEEE 14 上加 Switch，建带联络开关的拓扑
3. **Phase 3 升级**：加入"网络重构"规则（R004），依赖 Phase 2 的开关
4. **规则库 YAML 化**：把规则从代码迁出到 YAML/JSON 文件
5. **场景库**：积累一批典型故障剧本（单相接地、三相短路、N-1、N-2）作为测试基准

---

## 附录 A：关键 API 片段

```python
import VeraGridEngine as vg

grid = vg.open_file("IEEE 14 bus.raw")
pf = vg.power_flow(grid)                       # 潮流
sc = vg.short_circuit(grid, fault_index=2,
                     fault_type=vg.FaultType.LLLG, pf_results=pf)  # 短路

# 事件注入
gen.active = False          # 发电机跳机
line.active = False         # 线路跳闸
grid.add_load(bus, vg.Load(name="L", P=50, Q=15))   # 新增负荷

# 状态读取
pf.Sbus          # 各母线净注入 (MW + jMVar)
pf.Sf, pf.St     # 各支路从端/到端功率 (MVA)
pf.voltage       # 各母线电压（复数）
pf.converged     # bool
```

## 附录 B：术语对照

| 中文 | 英文 | 说明 |
|---|---|---|
| 潮流 | Power Flow | 给定 P/Q，求电压分布 |
| 自动投切 | Automatic Switching | 网络重构 / 保护动作 |
| 网络重构 | Network Reconfiguration | 改变拓扑改善运行指标 |
| 低压减载 | UVLS (Under-Voltage Load Shedding) | 紧急保护 |
| 恒功率负荷 | CPL (Constant Power Load) | 电力电子负载特性 |
| ZIP 模型 | ZIP Model | Z(恒阻抗)+I(恒电流)+P(恒功率) |
