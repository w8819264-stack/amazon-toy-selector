"""
亚马逊玩具利基报告 — 日期批量替换工具
目标：将所有日期统一改为英文格式
"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from datetime import datetime

TARGET = datetime.now().strftime('%B %d, %Y')  # e.g. "June 06, 2026"
BASE = r'G:\agent\projects\amazon-toy-selector'
FILE = os.path.join(BASE, 'index.html')

# ── 1. 读取 ──
with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# ── 2. 三处精确替换（英文格式）──
html = re.sub(
    r'<title>Amazon Toy Niche Product Report[^<]*</title>',
    f'<title>Amazon Toy Niche Product Report {TARGET}</title>',
    html
)
html = re.sub(
    r'<div class="value" id="dataDate">[^<]*</div>',
    f'<div class="value" id="dataDate">{TARGET}</div>',
    html
)
html = re.sub(
    r'<strong>Last Updated:</strong>\s*[^|]*\s*\|',
    f'<strong>Last Updated:</strong> {TARGET} |',
    html
)

# ── 3. 兜底：清理任何中文日期 ──
html = re.sub(r'\d{4}年\d{1,2}月\d{1,2}日', TARGET, html)

# ── 4. 写入 ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)

# ── 5. 验证 ──
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()

checks = {
    '1 <title>':            f'Report {TARGET}</title>' in final,
    '2 Data Collected card': f'id="dataDate">{TARGET}</div>' in final,
    '3 Last Updated':        f'Last Updated:</strong> {TARGET} |' in final,
}
# 任何中文日期残留
chinese_dates = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', final)

print('=' * 55)
print('  亚马逊报告日期批量替换 — 执行报告')
print('=' * 55)
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")
print(f"  {'✅' if len(chinese_dates) == 0 else '❌'} 中文日期残留: {len(chinese_dates)} 处")
print(f"  📏 文件: {len(final):,} 字符  |  结构完整: {final.startswith('<!DOCTYPE')}")
print('=' * 55)
if all(checks.values()) and len(chinese_dates) == 0:
    print(f'  🎉 全部通过！日期已统一为英文格式: {TARGET}')
else:
    print('  ❌ 存在问题，需要人工复查')
