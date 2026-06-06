"""
数据处理模块 — 清洗数据、计算FBA费用与利润指标
"""
import csv
import json
import os
import math


def load_config(config_path='config.json'):
    """加载配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def calc_fba_fee(weight_lbs, dimensions, config):
    """
    计算亚马逊 FBA 费用
    
    参数:
      weight_lbs: 重量(磅)
      dimensions: (length, width, height) 英寸
      config: 配置字典
    
    返回: dict {pick_pack, weight_fee, storage_est, referral_fee, total_fba, landed_cost}
    """
    fees = config['fba_fees']
    l, w, h = dimensions
    
    # 体积重量 (磅) = 长*宽*高 / 139
    dim_weight = (l * w * h) / 139.0
    billable_weight = max(weight_lbs, dim_weight)
    
    pick_pack = fees['pick_pack_per_unit']
    weight_fee = round(billable_weight * fees['weight_handling_per_lb'], 2)
    
    # 月度仓储费估算 (立方英尺)
    cuft = (l * w * h) / 1728.0
    storage_est = round(cuft * fees['monthly_storage_per_cuft'], 2)
    
    # FBA 基础费用 (不含佣金)
    fba_base = round(pick_pack + weight_fee, 2)
    
    total_fba = {
        'pick_pack': pick_pack,
        'weight_handling': weight_fee,
        'storage_monthly_est': storage_est,
        'fba_base': fba_base,
        'dimensional_weight': round(dim_weight, 2),
        'billable_weight': round(billable_weight, 2),
    }
    return total_fba


def calc_referral_fee(price, config):
    """计算销售佣金 (大部分类目 15%)"""
    rate = config['fba_fees']['referral_fee_percent']
    # 最低 $0.30
    return max(0.30, round(price * rate, 2))


def process_products(input_csv='data/raw_toys.csv', output_csv='data/processed_toys.csv', config_path='config.json'):
    """
    处理原始数据，计算利润指标
    
    新增字段:
      - fba_pick_pack, fba_weight_fee, fba_storage_est
      - referral_fee
      - total_fba_cost
      - landed_cost_est       (假设采购成本 = 售价 * 0.30)
      - net_profit
      - profit_margin         (净利润率)
      - competition_index     (竞争指数, 越低越好)
      - score_raw             (原始综合评分)
    """
    config = load_config(config_path)
    
    # 读取原始数据
    products = []
    with open(input_csv, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            products.append(row)
    
    print(f"📊 读取 {len(products)} 条原始数据")
    
    processed = []
    for p in products:
        price = float(p['price'])
        weight = float(p['weight_lbs'])
        dims = (float(p['length_in']), float(p['width_in']), float(p['height_in']))
        
        # FBA 费用
        fba = calc_fba_fee(weight, dims, config)
        ref_fee = calc_referral_fee(price, config)
        total_fba_cost = round(fba['fba_base'] + ref_fee + fba['storage_monthly_est'], 2)
        
        # 假设采购成本 = 售价 * 30% (实际应替换为真实采购价)
        purchase_cost = round(price * 0.30, 2)
        misc_cost = 1.00  # 包装、标签等杂费
        
        landed_cost = round(purchase_cost + total_fba_cost + misc_cost, 2)
        net_profit = round(price - landed_cost, 2)
        profit_margin = round(net_profit / price, 4) if price > 0 else 0
        
        # 竞争指数 (越低越好，0-100+)
        comp = int(p['competitors'])
        sales = int(p['sales_est'])
        reviews = int(p['review_count'])
        competition_index = round((comp * 100) / max(1, sales), 2)
        
        # 原始评分
        score_raw = round(
            (profit_margin * 35) +
            (min(sales / 500, 1) * 25) +
            (min(reviews / 500, 1) * 15) +
            (float(p['rating']) / 5 * 15) +
            (max(0, 1 - competition_index / 100) * 10),
            1
        )
        
        processed.append({
            **p,
            'fba_pick_pack': fba['pick_pack'],
            'fba_weight_fee': fba['weight_handling'],
            'fba_storage_est': fba['storage_monthly_est'],
            'referral_fee': ref_fee,
            'total_fba_cost': total_fba_cost,
            'purchase_cost_est': purchase_cost,
            'landed_cost_est': landed_cost,
            'net_profit': net_profit,
            'estimated_profit_margin': profit_margin,
            'competition_index': competition_index,
            'score_raw': score_raw,
        })
    
    # 保存处理后的数据
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    if processed:
        fieldnames = list(processed[0].keys())
        with open(output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed)
    
    print(f"✅ 处理完成: {output_csv} ({len(processed)} 条)")
    print(f"   ├─ 平均利润率: {sum(p['estimated_profit_margin'] for p in processed)/len(processed)*100:.1f}%")
    print(f"   ├─ 平均FBA费用: ${sum(p['total_fba_cost'] for p in processed)/len(processed):.2f}")
    print(f"   └─ 平均净利润: ${sum(p['net_profit'] for p in processed)/len(processed):.2f}")
    
    return processed


if __name__ == '__main__':
    # 确保有原始数据
    if not os.path.exists('data/raw_toys.csv'):
        from collector import collect_toy_data, save_raw_data
        data = collect_toy_data(150)
        save_raw_data(data)
    process_products()
