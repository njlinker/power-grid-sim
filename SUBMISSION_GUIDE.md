# GitHub 推送 + JOSS 投稿指南

本项目的本地仓库已就绪（包含 LICENSE、CITATION.cff、paper.md、64 个测试等）。本文档说明如何把它推到 GitHub 公开仓库并向 JOSS 投稿。

## 第一步：推送到 GitHub

### 1.1 在 GitHub 创建空仓库

1. 登录 GitHub
2. 点 `+` → `New repository`
3. 仓库名建议：`power-grid-sim`
4. Description: `Event-driven power grid simulation with auto-switching decision system`
5. **不要勾选** "Initialize this repository with a README"（避免冲突）
6. 选择 Public（公开），点 Create

### 1.2 添加远程并推送

在你的本地 `C:\code\research` 目录执行：

```bash
# 假设 GitHub 用户名是 your-name
git remote add origin https://github.com/your-name/power-grid-sim.git
git branch -M main
git push -u origin master:main
# 或直接：git push -u origin master

# E 盘的 bare 仓库也加一份（保留本地备份）
git remote add E-drive E:/Git/power-grid-sim.git
git push E-drive master
```

### 1.3 验证

- 打开 https://github.com/your-name/power-grid-sim
- 确认 README.md、LICENSE、paper.md 都显示出来
- 确认 tests/ 目录有 64 个测试

## 第二步：获取 Zenodo DOI（可选但推荐）

JOSS 要求软件有一个"长期可引用"的标识符。GitHub + Zenodo 集成会自动生成 DOI：

1. 在 GitHub 仓库页面点 Settings → 左侧找 "Zenodo"
2. 或者直接去 https://zenodo.org 用 GitHub 登录
3. 启用 Zenodo GitHub integration
4. 创建一个 Release（tag）：在 GitHub 点 Releases → Create a new release → tag `v1.0.0`
5. Zenodo 会自动归档这个 release 并给你一个 DOI（10.5281/zenodo.xxxxxx）
6. 把 DOI 更新到 `paper.md` 和 `CITATION.cff` 的相关字段

## 第三步：向 JOSS 投稿

### 3.1 准备工作检查清单

- [x] 软件有 OSI 兼容的开源许可证（MIT）
- [x] 有 README.md（介绍 + 安装 + 使用）
- [x] 有 docs/DESIGN.md（详细设计）
- [x] 有 paper.md（JOSS 格式）
- [x] 有测试套件（64 tests）
- [x] 有 Zenodo DOI（推荐，但 JOSS review 过程中后补也可以）
- [x] GitHub 仓库公开可访问

### 3.2 提交投稿

1. 去 https://github.com/openjournals/joss-reviews/issues/new/choose
2. 选择 "New submission" 模板
3. 填写 issue：
   - **Title**: `[SUBMISSION] PowerGridSim - v1.0.0`
   - **Body**:
     ```
     **Repository**: https://github.com/your-name/power-grid-sim
     **Version**: v1.0.0
     **Archive**: 10.5281/zenodo.xxxxxx (or "to be generated")
     **License**: MIT
     **Paper**: paper.md (in repository root)
     
     ### Summary
     PowerGridSim is an event-driven power grid simulation platform
     with auto-switching decision system, built on VeraGrid.
     
     ### Statement of Need
     (来自 paper.md 的 Statement of Need)
     
     ### Conflict of interest
     None
     ```

4. 等 JOSS 编辑分配 reviewer（通常几天到一周）

### 3.3 Review 流程

- Reviewer 会检查：安装、运行、文档、测试、许可证
- 可能会要求修改（通常 1-3 轮）
- 每次修改后 push 到 GitHub，issue 里回复说明
- 接受后会发布在 JOSS 期刊，给 DOI
- 总周期：1-6 个月

### 3.4 准备应对的问题

Reviewer 可能会问：
- "我能跑 `pytest` 不报错吗？" → 现在能
- "我能在新机器上 `pip install` 后运行吗？" → 提供了 requirements.txt
- "测试覆盖率多少？" → 目前 64 个测试，未做覆盖率统计，可补 `pytest-cov`
- "和 OpenDSS/GridCal 怎么对比？" → paper.md "Similar Work" 部分有说明

### 3.5 推荐的补强（可选）

如果时间允许，可以加：
1. `requirements.txt` 锁定版本（pip freeze > requirements.txt）
2. GitHub Actions CI 跑 pytest（每次 push 自动测）
3. 覆盖率报告（pytest-cov）
4. 简单 benchmark vs OpenDSS（如果有时间）

## 第四步：CI 配置（强烈推荐）

在 `.github/workflows/tests.yml` 创建：

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install VeraGrid numpy pandas pyyaml matplotlib plotly
           pytest stable-baselines3 gymnasium dash python-pptx
      - name: Run tests
        run: pytest
```

这样每次提交都会自动跑测试，JOSS reviewer 看到绿色 badge 会很加分。

## 第五步：补充 requirements.txt

```bash
gridcal-env\Scripts\python.exe -m pip freeze > requirements.txt
```

## 当前状态总结

| 项目 | 状态 |
|---|---|
| 代码 | ✅ 完整 |
| LICENSE (MIT) | ✅ |
| CITATION.cff | ✅ |
| README.md | ✅ |
| paper.md (JOSS 格式) | ✅ |
| docs/DESIGN.md | ✅ |
| 测试 (64 个) | ✅ 全部通过 |
| 本地 Git 仓库 | ✅ 12+ commits |
| E 盘备份 | ✅ |
| GitHub 公开仓库 | ⏳ 待推送 |
| Zenodo DOI | ⏳ 待创建 Release |
| JOSS 投稿 | ⏳ 待发起 issue |
| GitHub Actions CI | ⏳ 待配置（可选但推荐） |

## 预估时间线

- 推送 GitHub：30 分钟
- 创建 Zenodo Release：30 分钟
- 发起 JOSS 投稿：30 分钟
- 等 JOSS 编辑分 reviewer：1-2 周
- Review 过程（含修改）：1-3 个月
- 正式发表：3-6 个月

总共 4-7 个月能拿到 JOSS 发表。
