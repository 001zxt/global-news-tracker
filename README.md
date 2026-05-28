# 全球热点新闻抓取项目

这是一个适合练手和上传 GitHub 的小项目：用 Python 标准库抓取多个公开 RSS 新闻源，按热度排序，并生成一个本地 HTML 新闻仪表盘。

## 功能

- 抓取 BBC、Guardian、NPR、NYTimes、Al Jazeera、UN News、DW、TechCrunch AI 等 RSS 源
- 自动去重、提取标题、摘要、来源、地区、发布时间
- 根据发布时间、来源权重、热点关键词计算热度
- 生成可直接打开的网页：`dist/index.html`
- 生成机器可读数据：`dist/latest.json`
- 不需要安装第三方 Python 包

## 运行

在 PowerShell 里进入项目目录：

```powershell
cd "C:\Users\28760\Documents\自习室预约 project\global-news-tracker"
python news_fetcher.py
```

生成后打开：

```text
C:\Users\28760\Documents\自习室预约 project\global-news-tracker\dist\index.html
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 修改新闻源

编辑：

```text
sources.json
```

每个新闻源格式如下：

```json
{
  "name": "BBC World",
  "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
  "region": "World",
  "weight": 72
}
```

`weight` 越高，该来源的新闻初始热度越高。

## 上传到 GitHub

第一次上传可以这样做：

```powershell
git init
git add .
git commit -m "Create global news tracker"
```

如果你安装了 GitHub CLI，可以继续：

```powershell
gh repo create global-news-tracker --public --source=. --push
```

如果没有 GitHub CLI，就先在 GitHub 网页创建一个空仓库，然后运行 GitHub 给你的 `git remote add origin ...` 和 `git push ...` 命令。
