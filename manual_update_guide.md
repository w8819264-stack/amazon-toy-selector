# 📖 Manual Update & Push Guide

**How to manually run the pipeline and push to GitHub Pages — no coding skills needed.**

---

## Prerequisites (One-Time Setup)

### 1. Install Python 3.11+
- Download from [python.org](https://www.python.org/downloads/)
- ✅ Check "Add Python to PATH" during installation

### 2. Install Dependencies
Open **Command Prompt** (cmd) or **PowerShell** and run:
```bash
pip install pandas openpyxl curl_cffi beautifulsoup4
```

### 3. Install Git
- Download from [git-scm.com](https://git-scm.com/download/win)
- Default options are fine

### 4. Clone the Repository (first time only)
```bash
git clone https://github.com/w8819264-stack/amazon-toy-selector.git
cd amazon-toy-selector
```

---

## 🚀 Manual Update: Step-by-Step

### Step 1: Open Terminal in Project Folder
```bash
cd G:\agent\projects\amazon-toy-selector
```
*(Replace with your actual project path)*

### Step 2: Pull Latest Changes (if collaborating)
```bash
git pull origin master
```

### Step 3: Run the Pipeline
```bash
python main.py
```

**What this does:**
- Scrapes ~150 real toy products from Amazon.com (takes 1-2 minutes)
- Calculates FBA fees and profit margins
- Filters top 20 niche products
- Generates `index.html` with fresh data and today's date

**Expected output:**
```
============================================================
  ✅ 全部完成！index.html 已就绪
============================================================
```

### Step 4: Verify the Report
Open `index.html` in your browser:
```bash
start index.html
```
Check that:
- ✅ Dates are in English (e.g., "June 6, 2026")
- ✅ Prices look reasonable ($15.99–$49.99)
- ✅ Product titles and ratings display correctly

### Step 5: Commit Changes
```bash
git add index.html data/ main.py backend/
git commit -m "📊 Manual update: $(date +'%Y-%m-%d')"
```

*(On Windows PowerShell, use this instead:)*
```powershell
git add index.html data/ main.py backend/
git commit -m "📊 Manual update: $(Get-Date -Format 'yyyy-MM-dd')"
```

### Step 6: Push to GitHub
```bash
git push origin master
```

If asked for credentials:
- **Username**: Your GitHub username (`w8819264-stack`)
- **Password**: Use a [Personal Access Token](https://github.com/settings/tokens) (not your GitHub password)

### Step 7: Check GitHub Pages
Your report is live at:
```
https://w8819264-stack.github.io/amazon-toy-selector/
```
*(May take 1-2 minutes to reflect changes)*

---

## ⚡ Quick One-Liner (After Initial Setup)

```bash
cd G:\agent\projects\amazon-toy-selector && python main.py && git add index.html data/ && git commit -m "Update: %date%" && git push origin master
```

---

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| `python: command not found` | Python not in PATH — reinstall with "Add to PATH" checked |
| `ModuleNotFoundError: curl_cffi` | Run `pip install curl_cffi` |
| `git push` asks for password | Create a [GitHub Personal Access Token](https://github.com/settings/tokens) with `repo` scope |
| Pipeline takes forever | Amazon may be rate-limiting — wait 5 min and retry |
| `403 Forbidden` in logs | Amazon anti-bot detected — the scraper auto-rotates, retry later |
| `0 products selected` | Amazon page structure changed — check raw_toys.csv for data |
| GitHub Pages shows old version | Wait 2 min, then hard-refresh (Ctrl+Shift+R) |
| `Permission denied (publickey)` | Use HTTPS remote: `git remote set-url origin https://github.com/w8819264-stack/amazon-toy-selector.git` |

---

## 🤖 Automation (Already Configured)

A GitHub Actions workflow runs automatically **every day at UTC 00:00** (8:00 AM Beijing time).

You don't need to do anything — just check the site daily!

**Workflow file:** `.github/workflows/daily-scrape.yml`

**To trigger manually from GitHub.com:**
1. Go to https://github.com/w8819264-stack/amazon-toy-selector/actions
2. Click "Daily Amazon Toy Report"
3. Click "Run workflow" → "Run workflow"

---

## 📁 File Reference

| File | Purpose |
|------|---------|
| `main.py` | Pipeline orchestrator — **run this** |
| `backend/real_collector.py` | Amazon scraper (curl_cffi) |
| `backend/processor.py` | FBA fee calculator |
| `backend/selector.py` | Niche scoring & filtering |
| `config.json` | Filter settings (price range, weights, etc.) |
| `index.html` | The report — what visitors see |
| `data/raw_toys.csv` | Raw scraped data (150 products) |
| `data/processed_toys.csv` | After FBA fee calculation |
