import asyncio
from playwright.async_api import async_playwright
import pandas as pd
import re
import os
import time
from datetime import datetime

# =========================================================================
# 👇👇👇👇👇👇👇👇👇👇 配置区 👇👇👇👇👇👇👇👇👇👇
# =========================================================================

# 1. 扫描频率: 3 分钟
CHECK_INTERVAL = 180 

# 2. 熔断阈值 (防止被动位移刷屏)
MASSIVE_THRESHOLD = 8

# 3. 文件路径
CSV_FILE_PATH = r"C:\Users\wlh03\Desktop\AliMonitor\result.csv"

# 4. 锚点
ANCHOR_INDICES = [10, 20, 30, 40, 48] 

PAGE_KEYWORD = "manage_products"

# =========================================================================

# === 日期标准化 (兼容 Excel) ===
def normalize_date_str(date_str):
    s = str(date_str).strip()
    if not s or s.lower() == 'nan': return ""
    s = s.replace('/', '-')
    try:
        if '-' in s and len(s) <= 10:
            parts = s.split('-')
            if len(parts) == 3:
                return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except: pass
    return s

async def run():
    print(f">>> 正在启动 V18.1 (智能锁定 + 智能去重版)...")
    print(f">>> 🎯 [智能锁定] 自动寻找并激活阿里后台窗口")
    print(f">>> ♻️ [逻辑升级] 新ID + 旧型号 = 老品重发")
    print(f">>> 🔥 [逻辑升级] 新ID + 新型号 = 新品发布")
    print(f">>> 🛠️ [自动修复] 已开启日期格式标准化")

    # 初始化库
    content_snapshot = {} 
    history_time_db = {} 
    rank_snapshot = {}
    seen_models = set()
    
    last_anchors = []

    # === 加载历史档案 ===
    if os.path.exists(CSV_FILE_PATH):
        try:
            df_hist = pd.read_csv(CSV_FILE_PATH, dtype=str)
            for _, row in df_hist.iterrows():
                p_id = str(row.get('ID', '')).strip()
                if p_id:
                    # 1. 基础数据
                    raw_title = str(row.get('标题', '')).strip()
                    raw_price = str(row.get('价格', '')).strip()
                    raw_model = str(row.get('型号', '')).strip()
                    raw_owner = str(row.get('负责人', '')).strip()
                    raw_time = str(row.get('Ali更新时间', '')).strip()
                    
                    # 2. 标准化时间
                    norm_time = normalize_date_str(raw_time)
                    
                    # 3. 存入指纹
                    fingerprint = f"{raw_title}_{raw_price}_{raw_model}_{raw_owner}_{norm_time}"
                    content_snapshot[p_id] = fingerprint
                    
                    # 4. 存入时间库
                    if norm_time: history_time_db[p_id] = norm_time
                    
                    # 5. 存入型号库 (忽略大小写)
                    if raw_model: seen_models.add(raw_model.upper())
                        
            print(f">>> 📚 历史库载入完毕：监控 {len(content_snapshot)} 个ID，{len(seen_models)} 个独立型号")
        except Exception as e:
            print(f">>> ⚠️ 历史库读取警告: {e}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            print(">>> ✅ 成功连接到浏览器！")
        except Exception as e:
            print(f">>> ❌ 连接失败: {e}")
            return

        context = browser.contexts[0]
        if not context.pages:
            print(">>> ❌ 浏览器没有打开任何页面！")
            return

        # ==========================================
        # 🔥 V18.1 核心升级：自动寻找目标窗口
        # ==========================================
        target_page = None
        print(f">>> 正在 {len(context.pages)} 个标签页中寻找阿里后台...")
        
        for p_tab in context.pages:
            try:
                # 简单判断 URL 是否包含关键字
                if PAGE_KEYWORD in p_tab.url:
                    target_page = p_tab
                    # 获取标题只为了打印好看，出错也不影响逻辑
                    try: 
                        title = await p_tab.title()
                        print(f"    - 命中: [{title}]")
                    except: 
                        print(f"    - 命中: [未知标题]")
                    break
            except: pass
        
        if not target_page:
            print(f">>> ❌ 未找到包含 '{PAGE_KEYWORD}' 的页面。请确保你已经打开了阿里商品管理后台！")
            return
        
        # 激活该页面，设为当前操作对象
        page = target_page
        await page.bring_to_front()
        print(">>> 🎯 窗口锁定成功！开始监控...")
        # ==========================================

        SCROLL_CONTAINER = ".pp-layout-content"

        while True:
            try:
                # Double Check: 确保页面没跑偏
                if PAGE_KEYWORD in page.url:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🚀 开始新一轮扫描...")

                    # 1. 归位
                    try:
                        btn_page_1 = page.locator('button[aria-label*="第1页"]')
                        if await btn_page_1.count() == 0:
                            btn_page_1 = page.locator('.next-pagination-list button').filter(has_text=re.compile(r"^1$"))
                        if await btn_page_1.count() > 0:
                            class_attr = await btn_page_1.get_attribute("class")
                            if class_attr and "next-current" not in class_attr:
                                await btn_page_1.click()
                                await page.wait_for_timeout(4000)
                    except: pass

                    # 2. 刷新
                    try:
                        await page.reload(timeout=90000, wait_until='domcontentloaded')
                        await page.wait_for_selector('.list-item', timeout=30000)
                    except:
                        print(f">>> ⚠️ 刷新超时，跳过...")
                        await asyncio.sleep(5)
                        continue 

                    # 3. 50条
                    try:
                        btn_50 = page.locator(".next-pagination-size-selector-btn").filter(has_text="50")
                        if await btn_50.count() > 0:
                            await btn_50.click()
                            await page.wait_for_timeout(3000)
                    except: pass

                    # 4. 滚动
                    try:
                        await page.evaluate(f"document.querySelector('{SCROLL_CONTAINER}').scrollTop = 0")
                        await page.wait_for_timeout(1000)
                        scroll_info = await page.evaluate(f"() => {{ return {{ scrollHeight: document.querySelector('{SCROLL_CONTAINER}').scrollHeight }}; }}")
                        total_height = scroll_info['scrollHeight']
                        current_pos = 0
                        while current_pos < total_height:
                            current_pos += 600
                            await page.evaluate(f"document.querySelector('{SCROLL_CONTAINER}').scrollTop = {current_pos}")
                            await page.wait_for_timeout(300) 
                            if len(await page.locator('.list-item').all()) >= 50: break
                        await page.evaluate(f"document.querySelector('{SCROLL_CONTAINER}').scrollTop = 0")
                    except: pass

                    rows = await page.locator('.list-item').all()
                    if not rows: continue
                    
                    current_page_ids_set = set()
                    row_data_list = [] 

                    for row in rows:
                        text_content = await row.inner_text()
                        id_match = re.search(r'ID:\s*(\d+)', text_content)
                        if id_match:
                            p_id = id_match.group(1)
                            current_page_ids_set.add(p_id)
                            row_data_list.append((row, p_id))

                    # 幽灵补偿准备
                    missing_ids_map = {} 
                    if rank_snapshot:
                        for old_id, old_rank in rank_snapshot.items():
                            if old_id not in current_page_ids_set:
                                missing_ids_map[old_rank] = old_id
                    
                    # =================================================
                    # 🔥 阶段二: 筛选与比对
                    # =================================================
                    
                    candidates = [] 
                    found_boundary = False 
                    current_run_all_ids = [] 
                    current_run_rank_map = {}
                    global_rank_counter = 0

                    for row, p_id in row_data_list:
                        current_run_all_ids.append(p_id)
                        current_run_rank_map[p_id] = global_rank_counter
                        current_rank = global_rank_counter
                        global_rank_counter += 1

                        # --- 提取 ---
                        title = "未找到标题"
                        link = ""
                        try:
                            subject_div = row.locator('.product-subject')
                            if await subject_div.count() > 0:
                                a_tag = subject_div.locator('a').first
                                if await a_tag.count() > 0:
                                    link = await a_tag.get_attribute('href') or ""
                                    if link and not link.startswith('http'): link = "https:" + link
                                    pre_tag = a_tag.locator('pre')
                                    if await pre_tag.count() > 0: title = await pre_tag.inner_text()
                                    else: title = await a_tag.inner_text()
                        except: pass
                        title = title.strip()

                        model = ""
                        try:
                            model_el = row.locator('.product-model')
                            if await model_el.count() > 0:
                                raw = await model_el.inner_text()
                                model = raw.replace("型号:", "").replace("Model:", "").strip()
                        except: pass

                        price_val, owner_val, ali_time_val = "", "", ""
                        try:
                            cols = await row.locator('.next-col').all()
                            if len(cols) >= 6:
                                price_val = await cols[3].inner_text()
                                owner_val = await cols[4].inner_text()
                                ali_time_val = await cols[5].inner_text()
                        except: pass
                        
                        price_val = price_val.strip()
                        owner_val = owner_val.strip()
                        ali_time_val = ali_time_val.strip()
                        norm_ali_time = normalize_date_str(ali_time_val)

                        current_fingerprint = f"{title}_{price_val}_{model}_{owner_val}_{norm_ali_time}"
                        
                        is_recorded = False
                        status = ""
                        emoji = ""

                        # ==========================================
                        # 🔥 逻辑: 区分新品与重发
                        # ==========================================
                        if p_id not in content_snapshot:
                            is_recorded = True
                            if model.upper() in seen_models:
                                status = "老品重发" 
                                emoji = "♻️"
                            else:
                                status = "新品发布"
                                emoji = "🔥"
                        else:
                            old_fingerprint = content_snapshot[p_id]
                            if current_fingerprint != old_fingerprint:
                                is_recorded = True
                                status = "修改详情"
                                emoji = "✏️ (内容变动)"
                            else:
                                # 排名逻辑
                                if p_id in rank_snapshot:
                                    old_rank = rank_snapshot[p_id]
                                    ghosts_above = 0
                                    for missing_rank in missing_ids_map.keys():
                                        if missing_rank < old_rank:
                                            ghosts_above += 1
                                    expected_rank = old_rank - ghosts_above
                                    
                                    if current_rank < expected_rank:
                                        is_recorded = True
                                        status = "修改详情"
                                        emoji = "🚀 (排名上升)"

                        if is_recorded:
                            candidates.append({
                                'ID': p_id,
                                '型号': model,
                                '变化情况': status,
                                'Ali更新时间': ali_time_val, 
                                'norm_time': norm_ali_time,
                                '商品链接': link,
                                '标题': title,
                                '价格': price_val,
                                '抓取时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                '负责人': owner_val,
                                'log_str': f"{emoji} [{status}] {model} | {ali_time_val}",
                                'fingerprint': current_fingerprint
                            })
                            if model: seen_models.add(model.upper())

                        if last_anchors and p_id in last_anchors:
                            found_boundary = True
                            break
                    
                    found_boundary = True 

                    # =================================================
                    # 🔥 阶段三: 智能熔断
                    # =================================================
                    final_items = []
                    
                    if len(candidates) >= MASSIVE_THRESHOLD:
                        print(f"    >>> 🛡️ 触发熔断检查: 变动数 {len(candidates)}")
                        count_filtered = 0
                        for item in candidates:
                            # 新品、重发、内容变动 -> 放行
                            if "新品" in item['变化情况'] or "重发" in item['变化情况']:
                                final_items.append(item)
                                continue
                            
                            # 指纹变动 -> 放行
                            p_id = item['ID']
                            old_fp = content_snapshot.get(p_id)
                            if old_fp and item['fingerprint'] != old_fp:
                                final_items.append(item)
                                continue
                                
                            # 排名上升 -> 查时间
                            hist_time = history_time_db.get(p_id)
                            current_norm_time = item['norm_time']
                            if hist_time and hist_time == current_norm_time:
                                count_filtered += 1 
                            else:
                                final_items.append(item)
                        print(f"    >>> 🧹 过滤 {count_filtered} 条被动位移，保留 {len(final_items)} 条。")
                    else:
                        final_items = candidates

                    # === 收尾 ===
                    new_anchors = []
                    if current_run_all_ids:
                        for idx in ANCHOR_INDICES:
                            if idx < len(current_run_all_ids):
                                new_anchors.append(current_run_all_ids[idx])
                    if new_anchors: last_anchors = new_anchors

                    if current_run_rank_map:
                        rank_snapshot.update(current_run_rank_map)

                    if final_items:
                        for item in final_items:
                            print(item['log_str'])
                            content_snapshot[item['ID']] = item['fingerprint']
                            history_time_db[item['ID']] = item['norm_time']
                            if 'norm_time' in item: del item['norm_time']
                            if 'log_str' in item: del item['log_str']
                            if 'fingerprint' in item: del item['fingerprint']

                        df = pd.DataFrame(final_items)
                        column_order = ['ID', '型号', '变化情况', 'Ali更新时间', '商品链接', '标题', '价格', '抓取时间', '负责人']
                        df = df[column_order]
                        header = not os.path.exists(CSV_FILE_PATH)
                        df.to_csv(CSV_FILE_PATH, mode='a', header=header, index=False, encoding='utf-8-sig')
                        print(f"    >>> 🎉 成功记录 {len(final_items)} 条数据！")
                    else:
                        if not candidates: print("    >>> 🍃 无变化。")

                print(f">>> 💤 待机中...")
                remaining_time = CHECK_INTERVAL
                step = 60
                while remaining_time > 0:
                    await asyncio.sleep(min(remaining_time, step))
                    remaining_time -= step
                    if remaining_time > 0: print(f">>> ⏳ 倒计时: {remaining_time} 秒...")

            except Exception as e:
                print(f"!!! 错误: {e}")
                await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(run())