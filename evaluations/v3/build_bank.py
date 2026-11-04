"""Author round-3 bank (suite-v1 layout) after the Core code freeze.

Five new personas, new facts and chronology, and 24 semantic structures that differ in
surface and shape from rounds 1-2. Correction/update cases are included because they
are a real requirement, not because the fix targets them; their wording is new.
Timelines are checked so that no file describes events after it was sent.
"""

import bisect
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
BANK = ROOT / "bank"
SUITE = BANK / "suite-v1"
TZ = timezone(timedelta(hours=8))
START = datetime(2026, 8, 3, tzinfo=TZ)
FONT = "LOCAL_PATH"
SLOTS = 360
WEEK = "一二三四五六日"
# name, friend(女), third, org, project, object, doc, place, venue, city, sister, pet
PROFILES = [
    ("宁远", "陶溪", "卢岸", "社区合唱团", "晚风", "谱架", "曲目单", "银桥口", "枫林馆", "绍兴", "宁朵", "年糕"),
    ("叶澜", "周弥", "秦朗", "骑行俱乐部", "远山", "打气筒", "路书", "北湖站", "松间亭", "桂林", "叶萌", "豆包"),
    ("白芷", "林栖", "祝衡", "手作市集", "青柚", "展布", "摊位表", "西街口", "槐荫楼", "扬州", "白苏", "汤圆"),
    ("江屿", "许棠", "韦舟", "读书角", "萤火", "书立", "借书卡", "南门廊", "竹溪堂", "珠海", "江晚", "芝麻"),
    ("沈乔", "顾念", "邹野", "园艺小组", "春泥", "喷壶", "浇水表", "东园门", "桃源阁", "襄阳", "沈禾", "花卷"),
]
COLOR = ["墨蓝", "浅绿", "橙红", "米黄", "深灰"]
BOOKS = [("《雾港来信》", "《山中岁时记》", "《潮汐笔记》"), ("《北方的河谷》", "《夜航手册》", "《旧城地图》"),
         ("《纸上花园》", "《盐与光》", "《慢火》"), ("《云的形状》", "《星期三的雨》", "《远方来客》"),
         ("《种子的旅行》", "《晚霞信使》", "《石桥》")]
CHOICE = [("铝合金", "碳纤维"), ("黑色", "白色"), ("大号", "中号"), ("木质", "金属"), ("长嘴", "短嘴")]
CODES = ["5826", "3074", "6913", "4258", "7149"]
PRICES = [(18, 26, 9), (35, 12, 48), (22, 15, 30), (16, 40, 7), (28, 19, 11)]
CATEGORIES = [
    ("物品属性清单", "基本信息与偏好"), ("作息与周末例外", "基本信息与偏好"),
    ("亲属与宠物关系链", "基本信息与偏好"), ("读过与只被推荐", "基本信息与偏好"),
    ("两次改期链", "变化纠错与矛盾"), ("引用自己旧消息改数量", "变化纠错与矛盾"),
    ("转发通知改地点", "变化纠错与矛盾"), ("第三方改计划不影响用户", "来源与归属"),
    ("部分归还", "来源与归属"), ("助手建议被拒绝", "来源与归属"),
    ("边界设立后解除", "来源与归属"), ("大后天换算", "时间与顺序"),
    ("跨午夜时长", "时间与顺序"), ("包裹到达先后", "时间与顺序"),
    ("条件计划已触发", "计划假设与梦"), ("犹豫后作出决定", "计划假设与梦"),
    ("梦与现实", "计划假设与梦"), ("图片价签", "跨模态"),
    ("图片之后的增量更新", "跨模态"), ("语音中的柜号楼层", "跨模态"),
    ("表格查本人班次", "跨模态"), ("未知信息不编造", "未知与隐私"),
    ("可告知范围", "未知与隐私"), ("多跳线索", "多跳线索"),
]
FILLERS = [
    "今天骑车上班，风有点大。", "中午吃了碗牛肉粉。", "楼下新开了家面包店。", "今天加了会儿班。",
    "晚上看了半部电影，困了。", "阳台的薄荷又长高了。", "刚跟家里视频完。", "今天下了场小雨。",
    "地铁里有人在弹吉他。", "最近天黑得早了。", "周末打算大扫除。", "买了一袋橘子，挺甜。",
    "今天有点累，不想说话。", "刚洗完头。", "办公室空调好冷。", "早上在路边看到一只白猫。",
    "今天把衣柜整理了一半。", "晚饭做了番茄炒蛋。", "手机屏幕摔了个角。", "今天步数一万二。",
    "刚泡了杯茉莉花茶。", "楼道的灯坏了。", "今天听了一下午雨声。", "去超市囤了点挂面。",
    "最近在学做酸奶。", "邻居家小孩在练钢琴。", "今天天气特别好。", "刚收了个快递，是给家里买的。",
    "晚上散步看到很圆的月亮。", "准备睡了。",
]
REPLIES = ["嗯嗯，收到。", "好呀，早点休息。", "听起来不错。", "辛苦啦。", "哈哈，好的。"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def rows(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), "utf-8")


def src(text, mode="text", *, reply=None, visual=None):
    return {"body": text, "mode": mode, "reply": reply, "visual": visual}


def date(slot):
    return START + timedelta(days=slot // 2, hours=9 if slot % 2 == 0 else 20,
                             minutes=20 if slot % 2 == 0 else 0)


def iso(day):
    return day.date().isoformat()


def story(i, k, when):
    name, friend, third, org, project, obj, doc, place, venue, city, sister, pet = PROFILES[i]
    pid = project + "活动"
    book, book2, book3 = BOOKS[i]
    if k == 1:
        length, spare = 80 + 5 * i, 60 + 3 * i
        return ([src(f"{project}物品清单\n物品\t颜色\t长度\n{obj}\t{COLOR[i]}\t{length}厘米\n"
                     f"备用{obj}\t黑色\t{spare}厘米", "file")],
                f"我那个{obj}是什么颜色、多长？备用的和它一样吗？",
                [f"{obj}是{COLOR[i]}", f"长{length}厘米", f"备用的是黑色、{spare}厘米，与主用的不同"],
                [f"备用的也是{COLOR[i]}"], f"{friend}的{obj}是红色的，比我的短。")
    if k == 2:
        return ([src("我工作日早上六点半起床。"),
                 src("周末例外，周六周日我睡到八点，八点前别发消息吵我。")],
                "我工作日和周末各几点起床？周末早上七点能给我发消息吗？",
                ["工作日六点半起", "周末八点起", "周末八点前不要发消息"], ["周末七点可以发消息"], None)
    if k == 3:
        return ([src(f"我姐姐叫{sister}。"),
                 src(f"{sister}养了一只猫叫{pet}，今年三岁；我自己没养宠物。")],
                f"{pet}是谁的猫、几岁了？我自己养宠物吗？",
                [f"{pet}是姐姐{sister}的猫", "三岁", "用户自己没养宠物"], [f"用户养了{pet}"],
                f"{friend}家有条狗，叫{pet}二号，是我开玩笑起的名。")
    if k == 4:
        return ([src(f"{friend}推荐我读{book}，我还没开始读。"),
                 src(f"我最近读完的是{book2}，挺喜欢。")],
                f"我最近读完了哪本书？{book}我读过吗，是谁推荐的？",
                [f"读完的是{book2}", f"{book}还没读", f"{book}是{friend}推荐的"],
                [f"用户读过{book}"], None)
    if k == 5:
        d1 = when(0) + timedelta(days=10)
        d2, d3 = d1 + timedelta(days=2), d1 + timedelta(days=3)
        return ([src(f"{pid}排练定在{iso(d1)}晚上七点。"),
                 src(f"排练改到{iso(d2)}晚上七点了。"),
                 src(f"又改了一次，最后定在{iso(d3)}晚上七点半，之后不再改。")],
                f"{pid}排练最后定在哪天几点？之前改过几次、分别是什么时间？",
                [f"最终是{iso(d3)} 19:30", f"最初是{iso(d1)} 19:00", f"中间改到{iso(d2)} 19:00",
                 "共改过两次"], [f"最终是{iso(d2)}"], f"{org}的正式演出时间还没定。")
    if k == 6:
        return ([src(f"{pid}那天要带3箱矿泉水。"),
                 src("引用上一条“要带3箱矿泉水”：数量我写错了，是5箱。", "quote")],
                f"{pid}要带几箱矿泉水？3箱为什么不算？",
                ["5箱", "3箱是主人写错后自己更正的"], ["带3箱"], None)
    if k == 7:
        return ([src(f"{pid}在{venue}办。"),
                 src(f"{friend}转来场馆通知：{venue}本周六起闭馆维修，{pid}改到{place}，"
                     "时间不变。", "forward")],
                f"{pid}现在在哪办？{venue}还能用吗？",
                [f"改到{place}办", f"{venue}闭馆维修", "时间不变"], [f"仍在{venue}办"],
                f"隔壁的图书馆这周照常开放。")
    if k == 8:
        return ([src(f"我周日下午去{place}练习。"),
                 src(f"{friend}说：我周日下午有事，改成周六去了。这里的“我”是{friend}。",
                     "forward")],
                f"我周日下午还去{place}吗？{friend}的安排变了什么？",
                ["用户周日下午照常去", f"{friend}改成周六去"], ["用户改成周六去"], None)
    if k == 9:
        return ([src(f"我从{friend}那借了三本书，答应月底前还。"),
                 src(f"今天先还了两本，还剩{book3}没还。")],
                f"我借{friend}的书还了几本？还欠哪本？",
                ["已还两本", f"还剩{book3}没还"], ["三本都还了"], None)
    if k == 10:
        return ([src(f"{doc}怎么整理比较好？", "assistant",
                     reply="我建议按颜色分类，再贴标签。"),
                 src("按颜色分我不喜欢，我还是按日期整理。")],
                f"整理{doc}最后决定按什么方式？按颜色是谁提的？",
                ["按日期整理", "按颜色是助手提议、被用户拒绝"], ["用户决定按颜色整理"], None)
    if k == 11:
        return ([src("最近别提醒我体检的事。"),
                 src("体检那事可以重新提醒我了，下周记得说一声。")],
                "现在能提醒我体检吗？之前的限制还有效吗？",
                ["现在可以提醒体检", "之前的不提醒限制已解除"], ["仍然不能提醒体检"], None)
    if k == 12:
        target = when(0) + timedelta(days=3)
        mode = "relative_voice" if i % 2 == 0 else "text"
        return ([src(f"大后天上午十点我要去{venue}领{obj}，按今天算。", mode)],
                f"当时说的“大后天上午十点去{venue}”，换成公历是哪天几点？",
                [iso(target), "10:00"], ["按提问当天重新计算"], None)
    if k == 13:
        night = when(0) - timedelta(days=1)
        return ([src(f"{project}值夜记录\n开始\t{iso(night)} 22:40\n结束\t{iso(when(0))} 01:10",
                     "file")],
                "那次值夜从几点到几点，一共多长时间？跨天了吗？",
                ["22:40开始", "次日01:10结束", "共2小时30分钟", "跨过了午夜"], ["不到两小时"], None)
    if k == 14:
        return ([src(f"{obj}的包裹今天到了。"), src(f"{doc}的快递到了。"),
                 src("最后一个包裹，展架配件，今天也到了。")],
                f"{obj}、{doc}和展架配件这三个包裹，哪个最先到、哪个最后到？首尾相隔几天？",
                [f"{obj}最先到（{iso(when(0))}）", f"展架配件最后到（{iso(when(2))}）",
                 f"首尾相隔{(when(2).date() - when(0).date()).days}天"], ["顺序颠倒"], None)
    if k == 15:
        mode = "voice" if i % 2 else "text"
        return ([src(f"如果周六下雨，{pid}就改到{venue}室内。"),
                 src(f"周六真下雨了，{pid}改到{venue}室内办了。", mode)],
                f"{pid}周六在哪办的？改室内的条件触发了吗？",
                [f"在{venue}室内办", "下雨了，条件已触发"], ["在户外办"], None)
    if k == 16:
        first, second = CHOICE[i]
        return ([src(f"我在纠结买{first}还是{second}的{obj}。"),
                 src(f"想好了，买{second}的，已经下单。")],
                f"我最后选了哪种{obj}？下单了吗？",
                [f"选了{second}的", "已经下单"], [f"选了{first}的"], None)
    if k == 17:
        return ([src(f"昨晚梦见把{obj}弄丢了，吓醒了；早上一看，{obj}好好地在柜子里。", "voice")],
                f"我的{obj}真的丢了吗？",
                ["弄丢只是梦", f"{obj}实际还在柜子里"], ["现实中丢了"], None)
    if k == 18:
        items = ["胶带", "便签本", "收纳盒"]
        return ([src(f"{project}采购价签照片", "image",
                     visual={"type": "tags", "title": f"{project}采购价签",
                             "items": list(zip(items, PRICES[i], strict=True))})],
                f"{project}采购价签照片里，胶带、便签本、收纳盒各多少钱？",
                [f"胶带{PRICES[i][0]}元", f"便签本{PRICES[i][1]}元", f"收纳盒{PRICES[i][2]}元"],
                ["价格与图不符"], None)
    if k == 19:
        return ([src(f"{org}活动室照片", "image",
                     visual={"type": "layout", "title": f"{org}活动室",
                             "labels": ["折叠椅", "小桌", "台灯"], "counts": [3, 1, 1]}),
                 src("后来又搬来两把折叠椅，现在比照片上多。")],
                "照片上有几把折叠椅？现在一共几把？",
                ["照片上3把", "现在5把"], ["现在只有3把"], None)
    if k == 20:
        floor = 2 + i % 4
        return ([src(f"我新换的柜号是{' '.join(CODES[i])}，在{venue}{floor}楼。", "voice")],
                "我新换的柜号是多少？在几楼？",
                [f"柜号{CODES[i]}", f"{floor}楼"], ["编造其他柜号"],
                "原来那个旧柜子已经退了。")
    if k == 21:
        return ([src(f"轮值表上按我的名字{name}找。"),
                 src(f"{org}轮值表\n日期\t上午\t下午\n周二\t{third}\t{name}\n周四\t{name}\t{friend}\n"
                     f"周六\t{friend}\t{third}", "file")],
                "轮值表里我排在哪几天的哪个时段？周六下午是谁？",
                ["周二下午", "周四上午", f"周六下午是{third}"], ["用户排了周六"], None)
    if k == 22:
        return ([src(f"{friend}下个月过生日，具体哪天我也不记得了。")],
                f"{friend}的生日是哪天？",
                ["具体日期未知", "只知道在下个月"], ["编造具体日期"], None)
    if k == 23:
        return ([src(f"我在准备考研，这事可以跟我姐姐{sister}说，但别跟{org}的人提，尤其是{third}。")],
                f"如果{third}问我最近在忙什么，你怎么回？{sister}问呢？",
                [f"不向{third}透露考研", f"{sister}问起可以说在准备考研"], [f"告诉{third}考研"], None)
    if k == 24:
        start = 14 + i % 4
        day, other = WEEK[i % 5], WEEK[(i + 2) % 5]
        return ([src(f"{obj}锁在{venue}的3号柜。"), src(f"3号柜的钥匙在{friend}手上。"),
                 src(f"{org}值守表\n人\t时间\t地点\n{friend}\t周{day} {start}:00-{start + 2}:00\t{place}\n"
                     f"{third}\t周{other} 09:00-11:00\t{venue}", "file")],
                f"我想取{obj}，要找谁拿钥匙、什么时候、去哪找她？",
                [friend, f"周{day}", f"{start}:00-{start + 2}:00", place], [f"找{third}"], None)
    raise KeyError(k)


def draw_image(path, visual):
    image = Image.new("RGB", (1050, 720), "#f6f6f2")
    d = ImageDraw.Draw(image)
    big, normal, small = (ImageFont.truetype(FONT, size) for size in (31, 27, 19))
    d.text((40, 25), visual["title"], fill="#2b2b2b", font=big)
    if visual["type"] == "tags":
        for index, (item, price) in enumerate(visual["items"]):
            x = 60 + index * 330
            d.rounded_rectangle((x, 200, x + 280, 460), radius=20, fill="#fff7d6",
                                outline="#8a6d1d", width=4)
            d.text((x + 30, 250), item, fill="#2b2b2b", font=normal)
            d.text((x + 30, 340), f"¥{price}", fill="#b0361f", font=ImageFont.truetype(FONT, 54))
        d.text((40, 670), "价签上的数字为单价（元）。", fill="#666666", font=small)
    else:
        d.line((45, 130, 1000, 130), fill="#555555", width=3)
        d.line((525, 130, 525, 650), fill="#cccccc", width=3)
        d.line((45, 400, 1000, 400), fill="#cccccc", width=3)
        centers = [(250, 250), (740, 250), (525, 510)]
        for index, (label, count, center) in enumerate(zip(visual["labels"], visual["counts"],
                                                           centers, strict=True)):
            for j in range(count):
                x, y = center[0] - (count - 1) * 47 + j * 94, center[1]
                if index == 0:
                    d.rectangle((x - 30, y - 30, x + 30, y + 30), fill="#6b8eb5", outline="#2f4f6f",
                                width=3)
                elif index == 1:
                    d.ellipse((x - 34, y - 30, x + 34, y + 30), fill="#c9a96e", outline="#6e5a35",
                              width=3)
                else:
                    d.polygon([(x, y - 36), (x - 30, y + 30), (x + 30, y + 30)], fill="#e9d36b",
                              outline="#7a6a1d", width=3)
            d.text((center[0] - len(label) * 13, center[1] + 60), label, fill="#2b2b2b",
                   font=normal)
        d.text((40, 670), "数量以图中实际图形个数为准。", fill="#666666", font=small)
    image.save(path)


def main():
    BANK.mkdir(exist_ok=False)
    for directory in ("assets", "inputs", "review-only"):
        (SUITE / directory).mkdir(parents=True)
    questions, criteria, audio, provenance = [], [], [], []
    for index in range(len(PROFILES)):
        persona = f"S{index + 1:02}"
        slots_used, groups = {}, []
        for k in range(1, 25):
            base = 2 * (5 + 5 * k)
            plan = [base, base + 3, base + 5, base + 7]
            sources, question, required, forbidden, distractor = story(
                index, k, lambda j, plan=plan: date(plan[j]))
            slots = plan[:len(sources)]
            ids, modes = [], []
            for j, (slot, source) in enumerate(zip(slots, sources, strict=True)):
                sid = f"{persona}-R{k:02}-S{j + 1}"
                mode = source["mode"]
                asset = None
                if mode in ("image", "file", "voice", "relative_voice"):
                    asset = f"assets/{sid}." + {"image": "png", "file": "txt"}.get(mode, "wav")
                    if mode == "image":
                        draw_image(SUITE / asset, source["visual"])
                    elif mode == "file":
                        (SUITE / asset).write_text(source["body"] + "\n", "utf-8")
                    else:
                        audio.append({"asset": asset, "text": source["body"], "source_id": sid})
                item = {"id": sid, "now": date(slot).isoformat(), "modality": mode,
                        "text": "" if asset else source["body"], "asset": asset,
                        "caption": "这是我补充的一份资料，请按实际内容读取。" if asset else None,
                        "assistant_reply": source["reply"] or "收到，我记下了。"}
                assert slot not in slots_used
                slots_used[slot] = item
                ids.append(sid)
                modes.append("voice" if mode == "relative_voice" else mode)
                provenance.append({"source_id": sid, "author_text": source["body"],
                                   "visual": source["visual"],
                                   "inference_uses_author_text_for_media": False})
            if distractor:
                slot = base + 2 if base + 2 not in slots_used else base + 4
                assert slot not in slots_used
                slots_used[slot] = {"id": f"{persona}-R{k:02}-X1", "now": date(slot).isoformat(),
                                    "modality": "text", "text": distractor, "asset": None,
                                    "caption": None, "assistant_reply": "好，记下了。"}
            category, family = CATEGORIES[k - 1]
            groups.append({"k": k, "anchor": date(slots[-1]), "question": question,
                           "required": required, "forbidden": forbidden, "source_ids": ids,
                           "category": category, "family": family,
                           "input_modalities": sorted(set(modes))})
        history = []
        for slot in range(SLOTS):
            item = slots_used.get(slot) or {
                "id": f"{persona}-D{slot // 2:03}-{slot % 2}", "now": date(slot).isoformat(),
                "modality": "text", "text": FILLERS[(slot * 7 + index * 11) % len(FILLERS)],
                "asset": None, "caption": None,
                "assistant_reply": REPLIES[(slot + index) % len(REPLIES)]}
            history.append({"turn": slot + 1, **item})
        times = [datetime.fromisoformat(r["now"]) for r in history]
        for group in groups:
            for delay in (0, 3, 15, 45):
                when = group["anchor"] + timedelta(days=delay, minutes=15)
                qid = f"{persona}-R{group['k']:02}/d{delay:02}"
                questions.append({
                    "id": qid, "persona": persona, "group_id": f"{persona}-R{group['k']:02}",
                    "now": when.isoformat(), "cutoff_turn": bisect.bisect_right(times, when),
                    "question": group["question"], "source_ids": group["source_ids"],
                    "category": group["category"], "category_id": f"R{group['k']:02}",
                    "family": group["family"], "delay_days": delay, "kind": "semantic_memory",
                    "input_modalities": group["input_modalities"]})
                criteria.append({"id": qid, "required": group["required"],
                                 "forbidden": group["forbidden"], "source_ids": group["source_ids"]})
        rows(SUITE / "inputs" / f"{persona}.jsonl", history)
    rows(SUITE / "questions.jsonl", questions)
    rows(SUITE / "review-only/criteria.jsonl", criteria)
    rows(SUITE / "review-only/source-authoring-provenance.jsonl", provenance)
    rows(ROOT / "audio-to-synthesize.jsonl", audio)
    write_json(ROOT / "bank-authoring-status.json", {
        "status": "AUTHORED_PENDING_WAV_ASR_VALIDATION_AND_FREEZE",
        "authored_at": datetime.now(timezone.utc).isoformat(), "semantic": len(questions),
        "fact_groups": len(criteria) // 4, "source_records": len(provenance),
        "audio_assets": len(audio), "question_modality_memberships": dict(Counter(
            m for q in questions for m in q["input_modalities"])),
        "authoring_script_sha256": sha(Path(__file__)), "old_corpus_imported": False})
    print(json.dumps({"semantic": len(questions), "groups": len(criteria) // 4,
                      "audio_pending": len(audio)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
