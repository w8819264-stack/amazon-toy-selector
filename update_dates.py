"""
亚马逊玩具利基报告 — 日期批量替换工具
目标：将所有日期统一改为 2026年6月6日
"""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

TARGET = '2026年6月6日'
BASE = r'G:\agent\projects\amazon-toy-selector'
FILE = os.path.join(BASE, 'index.html')

# ── 1. 读取 ──
with open(FILE, 'r', encoding='utf-8') as f:
    html = f.read()

# ── 2. 三处精确替换 ──
html = html.replace(
    '<title>Amazon Toy Niche Product Report 2025</title>',
    f'<title>Amazon Toy Niche Product Report {TARGET}</title>'
)
html = html.replace(
    '<div class="value" id="dataDate">2025-07-17</div>',
    f'<div class="value" id="dataDate">{TARGET}</div>'
)
html = html.replace(
    '<strong>Last Updated:</strong> 2025-07-17 |',
    f'<strong>Last Updated:</strong> {TARGET} |'
)

# ── 3. 兜底：全局清扫任何漏网日期 ──
html = re.sub(r'\d{4}-\d{2}-\d{2}', TARGET, html)
html = re.sub(r'(?<!")(?<!\w)2025(?!\d)(?!年)', '2026', html)

# ── 4. 写入 ──
with open(FILE, 'w', encoding='utf-8') as f:
    f.write(html)

# ── 5. 验证 ──
with open(FILE, 'r', encoding='utf-8') as f:
    final = f.read()

checks = {
    '① <title>':            f'Report {TARGET}</title>' in final,
    '② Data Collected 卡片': f'id="dataDate">{TARGET}</div>' in final,
    '③ Last Updated':        f'Last Updated:</strong> {TARGET} |' in final,
}
residual = {
    'YYYY-MM-DD 旧格式': len(re.findall(r'\d{4}-\d{2}-\d{2}', final)),
    '"2025" 残留':       final.count('2025'),
    '未来年份(2027+)':   sum(final.count(str(y)) for y in range(2027, 2031)),
}

print('=' * 55)
print('  亚马逊报告日期批量替换 — 执行报告')
print('=' * 55)
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")
for k, v in residual.items():
    print(f"  {'✅' if v == 0 else '❌'} {k}: {v} 处")
print(f"  📏 文件: {len(final):,} 字符  |  结构完整: {final.startswith('<!DOCTYPE')}")
print('=' * 55)
if all(checks.values()) and all(v == 0 for v in residual.values()):
    print('  🎉 全部通过！日期已彻底统一为 2026年6月6日')
else:
    print('  ❌ 存在问题，需要人工复查')
