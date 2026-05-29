# 全球热点新闻追踪器

这是一个任何人都可以打开的公开网页小程序：

- 公开访问地址：<https://001zxt.github.io/global-news-tracker/>
- GitHub 仓库：<https://github.com/001zxt/global-news-tracker>
- GitHub Actions 每天自动抓取新闻并更新网站数据

## 功能

- 抓取多个公开 RSS 新闻源
- 自动去重、提取标题、摘要、来源、地区、发布时间
- 根据发布时间、来源权重和热点关键词计算热度
- 生成 `dist/latest.json` 供公开网页读取
- 网页支持搜索、地区筛选、热度排序、来源统计和热点词展示
- 不需要第三方 Python 包

## 本地运行

```powershell
cd "D:\codex项目\global-news-tracker"
python news_fetcher.py --limit 80
```

然后打开：

```text
D:\codex项目\global-news-tracker\index.html
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 自动更新

`.github/workflows/update-news.yml` 会在每天北京时间 08:30 自动运行：

```text
python news_fetcher.py --limit 80
```

它会提交新的 `dist/latest.json`，GitHub Pages 会自动显示最新新闻。

也可以手动运行：

1. 打开 GitHub 仓库
2. 点击 `Actions`
3. 选择 `Update News`
4. 点击 `Run workflow`
