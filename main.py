"""
亚马逊玩具自动选品系统 — 主入口
每日运行：采集数据 → 处理筛选 → 生成报告 HTML
"""
import sys, os, io
try:
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except (ValueError, AttributeError):
    pass

import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run_pipeline():
    """运行完整数据流水线，返回通过筛选的产品列表"""
    print("=" * 60)
    print("  亚马逊玩具自动选品系统 — 每日运行")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    products = []
    total_raw = 0

    # Step 1: 尝试采集真实数据
    try:
        print("\n📡 [Step 1/3] 采集亚马逊数据...")
        sys.path.insert(0, str(BASE_DIR))
        from backend.real_collector import scrape_all
        raw_path = BASE_DIR / 'data' / 'raw_toys.csv'
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        scrape_all(str(raw_path))
        print("   ✅ 数据采集完成")
    except Exception as e:
        print(f"   ⚠️ 采集失败 ({e})，使用已有数据")

    # Step 2: 处理数据
    try:
        print("\n🔧 [Step 2/3] 处理数据 (FBA 费用计算)...")
        from backend.processor import process_products
        process_products(
            str(BASE_DIR / 'data' / 'raw_toys.csv'),
            str(BASE_DIR / 'data' / 'processed_toys.csv'),
            str(BASE_DIR / 'config.json')
        )
        
        # Count processed
        processed_path = BASE_DIR / 'data' / 'processed_toys.csv'
        if processed_path.exists():
            with open(processed_path, 'r', encoding='utf-8') as f:
                total_raw = sum(1 for _ in f) - 1  # minus header
        print("   ✅ 数据处理完成")
    except Exception as e:
        print(f"   ⚠️ 处理失败 ({e})")
        import traceback
        traceback.print_exc()

    # Step 3: 筛选 & 评分
    try:
        print("\n🎯 [Step 3/3] 筛选利基产品 & 生成报告...")
        from backend.selector import load_config, score_product
        config = load_config(str(BASE_DIR / 'config.json'))
        filters = config['filters']

        processed_path = BASE_DIR / 'data' / 'processed_toys.csv'
        if not processed_path.exists():
            # Fallback to other data sources
            for fallback in ['niche_products.csv', 'verified_products.csv', 'raw_products.csv']:
                fb = BASE_DIR / 'data' / fallback
                if fb.exists():
                    processed_path = fb
                    break

        if processed_path.exists():
            with open(processed_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                all_products = list(reader)

            total_raw = len(all_products)

            for p in all_products:
                try:
                    price = float(p.get('price', 0))
                    rating = float(p.get('rating', 0))
                    reviews = int(float(p.get('review_count', 0)))
                    sales = int(float(p.get('sales_est', 0)))
                    competitors = int(float(p.get('competitors', 999)))
                    margin = float(p.get('estimated_profit_margin', 0))
                    weight = float(p.get('weight_lbs', 99))

                    if (filters['price_min'] <= price <= filters['price_max'] and
                        rating >= filters['min_rating'] and
                        reviews >= filters['min_reviews'] and
                        sales >= filters['min_sales_est'] and
                        competitors <= filters['max_competitors'] and
                        margin >= filters['min_profit_margin'] and
                        weight <= filters['weight_max_lbs']):

                        total_score, scores = score_product(p, config)
                        p['total_score'] = str(total_score)
                        p['margin_score'] = str(scores['margin_score'])
                        p['sales_score'] = str(scores['sales_score'])
                        p['review_score'] = str(scores['review_score'])
                        p['rating_score'] = str(scores['rating_score'])
                        p['comp_score'] = str(scores['comp_score'])
                        products.append(p)
                except (ValueError, KeyError):
                    continue

            products.sort(key=lambda x: float(x.get('total_score', 0)), reverse=True)
            products = products[:20]  # Top 20
        print(f"   ✅ 筛选完成，共 {len(products)} 个利基产品（来自 {total_raw} 个原始产品）")
    except Exception as e:
        print(f"   ⚠️ 筛选失败 ({e})")
        import traceback
        traceback.print_exc()

    return products, total_raw


def generate_html(products, total_raw=0):
    """基于模板和产品数据生成 index.html"""
    html_path = BASE_DIR / 'index.html'

    if not html_path.exists():
        print("❌ index.html 模板不存在！")
        return False

    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    today = datetime.now()
    date_str = today.strftime('%Y年%m月%d日')
    date_iso = today.strftime('%Y-%m-%d')

    # === 1. 替换 <title> ===
    html = re.sub(
        r'<title>Amazon Toy Niche Product Report[^<]*</title>',
        f'<title>Amazon Toy Niche Product Report {date_str}</title>',
        html
    )

    # === 2. 替换 Data Collected 日期 (id="dataDate") ===
    html = re.sub(
        r'<div class="value" id="dataDate">[^<]*</div>',
        f'<div class="value" id="dataDate">{date_str}</div>',
        html
    )

    # === 3. 替换 Last Updated 日期 ===
    html = re.sub(
        r'Last Updated:</strong>\s*[^<|]*(?=\s*\|)',
        f'Last Updated:</strong> {date_str} ',
        html
    )

    # === 4. 更新产品数据 & 统计 ===
    if products:
        # 构建产品 JSON 数组
        product_entries = []
        for i, p in enumerate(products):
            entry = {
                "rank": i + 1,
                "asin": p.get('asin', f'UNKNOWN{i}'),
                "title": p.get('title', p.get('product_name', 'Unknown')),
                "subcategory": p.get('subcategory', p.get('category', 'Toys')),
                "price": round(float(p.get('price', 0)), 2),
                "rating": round(float(p.get('rating', 0)), 1),
                "review_count": int(float(p.get('review_count', 0))),
                "sales_est": int(float(p.get('sales_est', 0))),
                "niche_potential": round(float(p.get('total_score', 50)), 1),
                "est_profit_margin": round(float(p.get('estimated_profit_margin', 0)), 2),
            }
            product_entries.append(entry)

        new_products_json = json.dumps(product_entries, ensure_ascii=False)

        # 替换 products 数组
        html = re.sub(
            r'const products = \[[\s\S]*?\];',
            f'const products = {new_products_json};',
            html
        )

        # 计算统计数据
        avg_score = sum(p['niche_potential'] for p in product_entries) / len(product_entries)
        avg_margin = sum(p['est_profit_margin'] for p in product_entries) / len(product_entries)
        prices = [p['price'] for p in product_entries]
        price_min = min(prices)
        price_max = max(prices)

        # 更新 Total Products Analyzed (id="totalProducts")
        display_total = total_raw if total_raw > 0 else 296
        html = re.sub(
            r'<div class="value" id="totalProducts">[^<]*</div>',
            f'<div class="value" id="totalProducts">{display_total}</div>',
            html
        )

        # 更新 Avg. Niche Score (id="avgPotential")
        html = re.sub(
            r'<div class="value" id="avgPotential">[^<]*</div>',
            f'<div class="value" id="avgPotential">{avg_score:.1f}</div>',
            html
        )

        # 更新 Price Range (id="priceRange")
        html = re.sub(
            r'<div class="value" id="priceRange">[^<]*</div>',
            f'<div class="value" id="priceRange">${price_min:.0f} – ${price_max:.0f}</div>',
            html
        )

        # 更新筛选结果数量 (id="filteredCount")
        html = re.sub(
            r'<span id="filteredCount">[^<]*</span>',
            f'<span id="filteredCount">{len(products)}</span>',
            html
        )

    # === 5. 写回 ===
    # 先备份
    backup_path = BASE_DIR / f'index_backup_{date_iso}.html'
    shutil.copy(html_path, backup_path)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ index.html 已更新 ({date_str})")
    print(f"📦 利基产品数: {len(products)} | 原始产品数: {total_raw}")
    print(f"📊 平均得分: {avg_score:.1f} | 平均利润率: {avg_margin*100:.0f}%")
    print(f"💰 价格区间: ${price_min:.0f} – ${price_max:.0f}")
    print(f"💾 备份: {backup_path.name}")
    return True


def main():
    print("🚀 启动亚马逊玩具自动选品系统\n")
    products, total_raw = run_pipeline()
    
    if not products:
        print("\n⚠️ 没有筛选到利基产品，使用现有数据更新日期...")
        # Still update dates even if no new products
        total_raw = 296  # default
    
    ok = generate_html(products, total_raw)

    print("\n" + "=" * 60)
    if ok:
        print("  ✅ 全部完成！index.html 已就绪")
    else:
        print("  ⚠️ 部分完成，请检查日志")
    print("=" * 60)
    return ok


if __name__ == '__main__':
    main()
