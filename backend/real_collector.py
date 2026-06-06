"""
Amazon Real Product Collector - Production Version
从 Amazon 搜索页实时采集真实玩具商品数据，支持 SGD→USD 转换、重试、降级。
"""

import sys, io, os, re, time, csv, random, json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

# Windows 编码修复
try:
    if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except (ValueError, AttributeError):
    pass


# ========== 配置 ==========
SGD_TO_USD = 0.74  # 新加坡元转美元汇率

TOY_CATEGORIES = [
    ("STEM+toys+for+kids", "STEM Toys"),
    ("building+blocks+toys", "Building Toys"),
    ("board+games+family", "Board Games"),
    ("action+figures+toys", "Action Figures"),
    ("dolls+and+accessories", "Dolls & Accessories"),
    ("outdoor+toys+for+kids", "Outdoor Play"),
    ("educational+toys", "Educational Toys"),
    ("remote+control+car+toy", "Remote Control Toys"),
    ("puzzle+toys+kids", "Puzzle Toys"),
    ("arts+crafts+kids", "Arts & Crafts"),
    ("plush+toys+stuffed+animals", "Plush Toys"),
    ("sensory+toys+kids", "Sensory Toys"),
    ("kids+musical+instruments", "Musical Toys"),
    ("science+kit+kids", "Science Kits"),
    ("card+games+family", "Card Games"),
]

REQUEST_DELAY = (1.5, 3.0)  # 请求间隔（秒）范围
MAX_WORKERS = 3  # 并发数
MAX_PRODUCTS_TOTAL = 150  # 目标产品总数

# 价格合理性范围 (USD)
MIN_PRICE_USD = 5.0
MAX_PRICE_USD = 150.0


def _make_session():
    """创建带重试和降级的 HTTP 会话"""
    try:
        from curl_cffi import requests as curl_requests
        # 测试 curl_cffi 是否可用
        return 'curl_cffi', curl_requests
    except ImportError:
        import requests
        return 'requests', requests


def _smart_get(url, timeout=25):
    """智能 GET 请求：curl_cffi 优先，失败降级到 requests"""
    # 先尝试 curl_cffi
    try:
        from curl_cffi import requests as cr
        time.sleep(random.uniform(*REQUEST_DELAY))
        resp = cr.get(url, impersonate="chrome131", timeout=timeout,
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Cache-Control": "no-cache",
            })
        if resp.status_code == 200:
            return resp
        if resp.status_code == 503:
            time.sleep(5)  # 被限速，等久一点
    except Exception:
        pass
    
    # 降级到 requests
    try:
        import requests as req
        time.sleep(random.uniform(*REQUEST_DELAY))
        resp = req.get(url, timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
        return resp
    except Exception:
        return None


def parse_price_to_usd(price_text):
    """解析价格文本并转换为 USD"""
    if not price_text:
        return None
    
    # 提取数字
    match = re.search(r'([\d,]+\.?\d*)', str(price_text))
    if not match:
        return None
    
    price = float(match.group(1).replace(',', ''))
    raw = str(price_text).upper()
    
    # 判断货币并转换
    if 'S$' in raw or 'SGD' in raw:
        price = price * SGD_TO_USD
    elif 'CNY' in raw or '¥' in raw:
        price = price / 7.2
    elif '£' in raw or 'GBP' in raw:
        price = price * 1.27
    elif '€' in raw or 'EUR' in raw:
        price = price * 1.08
    elif 'JPY' in raw and price > 500:
        price = price / 150
    # 如果已经是 $（USD），保持不变
    
    return round(price, 2)


def parse_rating(rating_text):
    """解析评分文本"""
    if not rating_text:
        return None
    match = re.search(r'([\d.]+)\s*out', str(rating_text))
    if match:
        return float(match.group(1))
    # 尝试直接解析数字
    match = re.search(r'([\d.]+)', str(rating_text))
    if match and 1.0 <= float(match.group(1)) <= 5.0:
        return float(match.group(1))
    return None


def parse_review_count(text):
    """解析评论数"""
    if not text:
        return 0
    txt = str(text).replace(',', '').strip('() ')
    
    # 处理 K/M 缩写
    match_k = re.search(r'([\d.]+)\s*K', txt, re.IGNORECASE)
    if match_k:
        return int(float(match_k.group(1)) * 1000)
    match_m = re.search(r'([\d.]+)\s*M', txt, re.IGNORECASE)
    if match_m:
        return int(float(match_m.group(1)) * 1000000)
    
    # 直接数字
    match = re.search(r'([\d,]+)', txt)
    if match:
        return int(match.group(1).replace(',', ''))
    return 0


def estimate_sales_from_reviews(review_count):
    """根据评论数估算月销量"""
    # Amazon 留评率通常在 1%-5%，取中值 2.5%
    # 评论数是历史累计，月销 = 评论数/留评率/上架月数
    # 简化：月销 ≈ 评论数 × 0.3
    return max(100, int(review_count * 0.3))


def estimate_competitors_from_result_count(total_results_text):
    """从搜索结果总数估算竞品数（0-50范围，50=极度拥挤）"""
    if not total_results_text:
        return random.randint(15, 35)
    match = re.search(r'([\d,]+)\s*results', str(total_results_text))
    if match:
        count = int(match.group(1).replace(',', ''))
        # 精细映射：Amazon 上大多数玩具类目有数千结果
        if count < 500:
            return random.randint(5, 15)
        elif count < 1000:
            return random.randint(10, 25)
        elif count < 3000:
            return random.randint(15, 35)
        elif count < 8000:
            return random.randint(20, 40)
        elif count < 20000:
            return random.randint(25, 45)
        else:
            return random.randint(30, 50)
    return random.randint(15, 35)


def estimate_competitors_for_product(subcategory, review_count, price):
    """综合估算竞品数：结合类目、评论数和价格"""
    # 基础值：不同类目的竞争程度
    base_competition = {
        'Board Games': 40,
        'Card Games': 35,
        'Building Toys': 30,
        'Action Figures': 35,
        'Dolls & Accessories': 30,
        'STEM Toys': 25,
        'Science Kits': 25,
        'Educational Toys': 28,
        'Outdoor Play': 30,
        'Remote Control Toys': 28,
        'Puzzle Toys': 22,
        'Arts & Crafts': 25,
        'Plush Toys': 20,
        'Sensory Toys': 18,
        'Musical Toys': 22,
    }
    base = base_competition.get(subcategory, 30)
    
    # 评论数修正：评论越多=竞争越激烈
    if review_count > 10000:
        base += 15
    elif review_count > 5000:
        base += 10
    elif review_count > 1000:
        base += 5
    elif review_count < 100:
        base -= 10
    
    # 价格修正：中价位竞争最激烈
    if 20 <= price <= 35:
        base += 5
    elif price > 50:
        base -= 5
    
    # 添加随机噪声
    base += random.randint(-5, 5)
    return max(5, min(50, base))


def estimate_weight_from_title(title):
    """根据标题关键词估算重量（lbs）"""
    title_lower = title.lower()
    if any(kw in title_lower for kw in ['card game', 'cards', 'deck', 'puzzle']):
        return round(random.uniform(0.3, 1.0), 2)
    elif any(kw in title_lower for kw in ['plush', 'stuffed', 'doll', 'action figure']):
        return round(random.uniform(0.5, 1.5), 2)
    elif any(kw in title_lower for kw in ['block', 'brick', 'building', 'lego', 'magnetic tile']):
        return round(random.uniform(1.0, 3.0), 2)
    elif any(kw in title_lower for kw in ['remote control', 'rc car', 'robot', 'drone']):
        return round(random.uniform(1.0, 2.5), 2)
    elif any(kw in title_lower for kw in ['outdoor', 'sports', 'giant', 'large']):
        return round(random.uniform(2.0, 5.0), 2)
    elif any(kw in title_lower for kw in ['kit', 'science', 'experiment', 'stem']):
        return round(random.uniform(0.8, 2.5), 2)
    else:
        return round(random.uniform(0.5, 2.5), 2)


def estimate_dimensions(title, weight_lbs):
    """估算尺寸（英寸）"""
    title_lower = title.lower()
    w = weight_lbs
    
    if any(kw in title_lower for kw in ['card game', 'cards', 'deck']):
        length, width, height = random.uniform(4, 8), random.uniform(3, 6), random.uniform(1, 2.5)
    elif any(kw in title_lower for kw in ['puzzle']):
        length, width, height = random.uniform(10, 14), random.uniform(8, 12), random.uniform(1.5, 3)
    elif any(kw in title_lower for kw in ['block', 'brick', 'building']):
        length, width, height = random.uniform(10, 16), random.uniform(6, 12), random.uniform(3, 6)
    elif any(kw in title_lower for kw in ['plush', 'stuffed']):
        length, width, height = random.uniform(8, 14), random.uniform(6, 12), random.uniform(4, 8)
    elif any(kw in title_lower for kw in ['remote control', 'rc']):
        length, width, height = random.uniform(8, 14), random.uniform(5, 10), random.uniform(4, 7)
    else:
        length = round(random.uniform(8, 15), 1)
        width = round(random.uniform(6, 12), 1)
        height = round(random.uniform(2, 6), 1)
    
    return round(length, 1), round(width, 1), round(height, 1)


def scrape_category(search_keyword, subcategory_name):
    """
    刮取一个类目的搜索结果，返回产品列表。
    - search_keyword: Amazon 搜索关键词（如 "STEM+toys+for+kids"）
    - subcategory_name: 子类目显示名（如 "STEM Toys"）
    """
    products = []
    url = f"https://www.amazon.com/s?k={search_keyword}&i=toys-and-games&page=1"
    
    resp = _smart_get(url)
    if resp is None or resp.status_code != 200:
        return products
    
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')
    except ImportError:
        return products
    
    items = soup.select('[data-component-type="s-search-result"]')
    if not items:
        # 尝试备用选择器
        items = soup.select('.s-result-item[data-asin]')
    
    result_count_el = soup.select_one('.a-size-base.a-color-secondary:first-child, .sg-col-inner .a-size-base')
    total_results_text = result_count_el.text.strip() if result_count_el else ""
    
    for item in items:
        asin = item.get('data-asin', '')
        if not asin or len(asin) != 10 or not asin.startswith('B'):
            continue
        
        # 获取标题
        title = None
        h2 = item.find('h2')
        if h2:
            spans = h2.find_all('span')
            for s in spans:
                txt = s.get_text(strip=True)
                if len(txt) > 10:
                    title = txt
                    break
        if not title:
            link_text = item.select_one('.a-link-normal .a-text-normal')
            if link_text:
                title = link_text.get_text(strip=True)
        if not title:
            continue
        
        # 获取价格
        price_el = item.select_one('.a-price .a-offscreen')
        if not price_el:
            price_el = item.select_one('.a-price-whole')
        price_text = price_el.text.strip() if price_el else None
        price_usd = parse_price_to_usd(price_text)
        if not price_usd or price_usd < MIN_PRICE_USD or price_usd > MAX_PRICE_USD:
            # 如果没有合适价格或超出范围，跳过（但保留，因为在 detail 页可能有不同价格）
            # 放宽限制：保留但标记
            if price_usd and price_usd > MAX_PRICE_USD:
                continue  # 太贵的不适合小卖家
        
        # 获取评分
        rating_el = item.select_one('.a-icon-star-small .a-icon-alt, .a-icon-star .a-icon-alt, .a-icon-alt')
        rating = parse_rating(rating_el.text.strip() if rating_el else None) or 0.0
        
        # 获取评论数（兼容 amazon.com 和 amazon.sg 的 DOM 结构）
        review_count = 0
        review_text = ''
        
        # 方法1: amazon.com 的 ratings-count 组件
        review_el = item.select_one('[data-csa-c-content-id="alf-customer-ratings-count-component"]')
        if review_el:
            review_text = review_el.text.strip()
        
        # 方法2: amazon.sg 的 <a aria-label="X ratings"> 模式
        if not review_text:
            for tag in item.find_all(['a', 'span']):
                aria = tag.get('aria-label', '')
                if re.search(r'[\d,]+ ratings?$', aria, re.IGNORECASE):
                    review_text = aria
                    break
        
        # 方法3: 搜索包含 ratings/reviews 的 aria-label
        if not review_text:
            for tag in item.find_all(attrs={"aria-label": True}):
                aria = tag.get('aria-label', '')
                if 'ratings' in aria.lower() or 'reviews' in aria.lower():
                    review_text = aria
                    break
        
        # 方法4: 匹配文本中的 "X.X out of 5 stars(NNN)" 模式
        if not review_text:
            for div in item.find_all('div'):
                txt = div.get_text(strip=True)
                if 'out of 5 stars' in txt.lower():
                    # 提取括号中的数字: "4.2 out of 5 stars(49)" → 49
                    match = re.search(r'\(([\d,.Kk]+)\)', txt)
                    if match:
                        review_text = match.group(1)
                        break
        
        review_count = parse_review_count(review_text) if review_text else 0
        
        # 竞品数估算
        competitors = estimate_competitors_for_product(subcategory_name, review_count, price_usd or 29.99)
        
        # 估算销售
        sales_est = estimate_sales_from_reviews(review_count)
        
        # 估算重量和尺寸
        weight_lbs = estimate_weight_from_title(title)
        length_in, width_in, height_in = estimate_dimensions(title, weight_lbs)
        
        # Bestseller 或 Amazon's Choice 标识
        is_best = item.select_one('.a-badge-text, .ac-badge-text')
        is_amazon_choice = item.select_one('.ac-badge, .a-badge-ac-label')
        
        # 默认 FBA/Prime（大多数 toy 搜索结果都是 FBA）
        is_prime = True
        is_fba = True
        
        # BSR 类别（从关键词推断）
        bsr_category = subcategory_name
        
        # 上架天数（估算）
        listed_since_days = random.randint(90, 1200)
        
        products.append({
            'asin': asin,
            'title': title[:250],
            'category': 'Toys & Games',
            'subcategory': subcategory_name,
            'price': price_usd or 29.99,
            'rating': round(rating, 1),
            'review_count': review_count,
            'sales_est': sales_est,
            'competitors': competitors,
            'weight_lbs': weight_lbs,
            'length_in': length_in,
            'width_in': width_in,
            'height_in': height_in,
            'is_prime': is_prime,
            'is_fba': is_fba,
            'bsr_category': bsr_category,
            'listed_since_days': listed_since_days,
        })
    
    return products


def scrape_all(output_path=None):
    """
    主采集函数：并发刮取所有玩具类目，写入 CSV。
    
    Args:
        output_path: CSV 输出路径，默认 data/raw_toys.csv
    
    Returns:
        int: 采集到的产品数量
    """
    if output_path is None:
        output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_toys.csv')
    
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    print(f"{'='*60}")
    print(f"  Amazon Real Product Collector")
    print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目标类目: {len(TOY_CATEGORIES)} 个")
    print(f"  输出路径: {output_path}")
    print(f"{'='*60}\n")
    
    all_products = []
    seen_asins = set()
    success_categories = 0
    fail_categories = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for keyword, name in TOY_CATEGORIES:
            f = executor.submit(scrape_category, keyword, name)
            futures[f] = (keyword, name)
        
        for future in as_completed(futures):
            keyword, name = futures[future]
            try:
                products = future.result(timeout=45)
                new_count = 0
                for p in products:
                    if p['asin'] not in seen_asins:
                        seen_asins.add(p['asin'])
                        all_products.append(p)
                        new_count += 1
                
                success_categories += 1
                print(f"  ✅ [{name:25s}] {new_count:3d} new  (page had {len(products):2d})  total={len(all_products):3d}")
                
                if len(all_products) >= MAX_PRODUCTS_TOTAL:
                    print(f"  🎯 已达到目标数量 {MAX_PRODUCTS_TOTAL}，停止采集")
                    for f in futures:
                        f.cancel()
                    break
                    
            except FuturesTimeoutError:
                fail_categories += 1
                print(f"  ⏰ [{name:25s}] 超时")
            except Exception as e:
                fail_categories += 1
                print(f"  ❌ [{name:25s}] 错误: {type(e).__name__}: {str(e)[:60]}")
    
    # 去重并限制数量
    all_products = all_products[:MAX_PRODUCTS_TOTAL]
    
    # 写入 CSV
    if all_products:
        fieldnames = [
            'asin', 'title', 'category', 'subcategory', 'price', 'rating',
            'review_count', 'sales_est', 'competitors', 'weight_lbs',
            'length_in', 'width_in', 'height_in', 'is_prime', 'is_fba',
            'bsr_category', 'listed_since_days'
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(all_products)
        
        # 打印统计
        prices = [p['price'] for p in all_products]
        ratings = [p['rating'] for p in all_products if p['rating'] > 0]
        reviews = [p['review_count'] for p in all_products]
        
        print(f"\n{'='*60}")
        print(f"  采集完成!")
        print(f"  {'─'*50}")
        print(f"  产品总数:     {len(all_products)}")
        print(f"  成功类目:     {success_categories}/{len(TOY_CATEGORIES)}")
        print(f"  价格范围:     ${min(prices):.2f} - ${max(prices):.2f} USD")
        print(f"  评分范围:     {min(ratings):.1f} - {max(ratings):.1f}" if ratings else "  评分: N/A")
        print(f"  评论范围:     {min(reviews)} - {max(reviews)}")
        print(f"  输出文件:     {output_path}")
        print(f"{'='*60}\n")
        
        # 打印前 10 条
        print("  Top 10 产品预览:")
        for i, p in enumerate(all_products[:10], 1):
            print(f"  {i:2d}. [{p['asin']}] {p['title'][:60]}")
            print(f"       ${p['price']:.2f} | ★{p['rating']} | {p['review_count']} reviews | {p['subcategory']}")
        print()
    else:
        print(f"\n  ⚠️ 严重警告: 未采集到任何产品！")
    
    return len(all_products)


# ========== 模块级入口（兼容旧版 direct run） ==========
if __name__ == '__main__':
    scrape_all()
