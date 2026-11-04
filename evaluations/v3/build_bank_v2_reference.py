"""Author a fresh fictional bank (suite-v2) after the Core code freeze.

New personas, domains, facts, chronology and 24 semantic structures that the previous
suite did not use; nothing is imported from the old corpus. Some groups carry a sibling
distractor turn (a similar fact about a different object/person) to test discrimination.
Media captions are generic; images carry the facts visually, never as answer captions.
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
START = datetime(2026, 4, 6, tzinfo=TZ)
FONT = "LOCAL_PATH"
SLOTS = 360
WEEK = "一二三四五六日"
# name, friend(女), third, org, project, object, doc, place, venue, city
PROFILES = [
    ("林晚", "郑一舟", "柏原", "城南读书会", "青苔", "投影仪", "借阅单", "梧桐巷", "云杉楼", "厦门"),
    ("何满", "沈栀", "邵临", "夜跑小组", "白鹭", "计时器", "打卡表", "江堤口", "柳湾站", "昆明"),
    ("苏禾", "韩笙", "钟砚", "社区厨房", "麦穗", "保温箱", "配餐单", "后院棚", "青砖房", "大连"),
    ("唐映", "罗川", "褚远", "天文观测社", "星屑", "望远镜", "观测记录", "山顶平台", "槐树院", "西宁"),
    ("姜澄", "宋屿", "黎墨", "旧书修复坊", "纸鸢", "压书机", "修复清单", "西门库房", "竹影阁", "泉州"),
    ("程曦", "魏然", "季朗", "猫咪救助站", "栗子", "航空箱", "领养登记", "东侧仓库", "海棠里", "洛阳"),
]
OTHER_OBJECT = ["音箱", "反光背心", "砧板", "赤道仪", "裁纸刀", "猫爬架"]
OTHER_DOC = ["会员册", "路线单", "采购单", "设备清单", "裱糊记录", "疫苗本"]
MILK = ["燕麦奶", "椰奶", "杏仁奶", "燕麦奶", "豆奶", "椰奶"]
TEA = ["大麦茶", "菊花茶", "玉米须茶", "陈皮水", "大麦茶", "红枣水"]
AVOID = ["香菜", "芹菜", "小葱", "蒜苗", "茴香", "洋葱"]
COLORS = [("墨绿", "米白"), ("酒红", "浅灰"), ("藏青", "鹅黄"), ("橘色", "雾蓝"), ("深紫", "奶茶色"),
          ("湖蓝", "杏色")]
CODES = ["4827", "3615", "7092", "5384", "2671", "9156"]
CATEGORIES = [
    ("偏好与时段例外", "基本信息与偏好"), ("数值与单位", "基本信息与偏好"),
    ("人物关系链", "基本信息与偏好"), ("饮食忌口与例外", "基本信息与偏好"),
    ("截止日期顺延", "变化纠错与矛盾"), ("多次变更与历史", "变化纠错与矛盾"),
    ("部分取消", "变化纠错与矛盾"), ("第三方偏好归属", "来源与归属"),
    ("助手承诺与用户承诺", "来源与归属"), ("引用旧消息更正", "变化纠错与矛盾"),
    ("星期换算日期", "时间与顺序"), ("跨日时长", "时间与顺序"),
    ("分散事件排序", "时间与顺序"), ("条件计划未触发", "计划假设与玩笑"),
    ("计划与完成回执", "计划假设与玩笑"), ("假设提问", "计划假设与玩笑"),
    ("玩笑不当真", "计划假设与玩笑"), ("图片计数", "跨模态"),
    ("图文冲突以文字更正为准", "跨模态"), ("语音中的数字", "跨模态"),
    ("表格查询与本人对应", "跨模态"), ("未知信息不编造", "未知与隐私"),
    ("保密范围与授权对象", "未知与隐私"), ("多跳线索", "多跳线索"),
]
FILLERS = [
    "今天下班路上买了点水果。", "刚把阳台的花浇了。", "晚上随便煮了碗面。", "今天有点困，早点睡。",
    "楼下在修路，有点吵。", "下午开了个很长的会，好累。", "刚看完一集纪录片，讲海龟的。",
    "今天风好大。", "周末想去公园走走，还没定。", "手机快没电了，先这样。", "刚收拾了一下书桌。",
    "今天食堂的汤还不错。", "路上看到一只橘猫在晒太阳。", "最近在听一张老专辑。",
    "今天换了个新水杯。", "早上差点迟到。", "下雨了，幸好带了伞。", "刚给家里打了个电话。",
    "今天没什么特别的事。", "晚饭吃多了，出去走两圈。", "楼上邻居又在装修。",
    "刚洗完衣服。", "今天的天空特别蓝。", "看了会儿书就犯困。", "冰箱里的酸奶过期了，扔了。",
    "今天心情还行。", "刚泡了杯热水。", "地铁上人好多。", "今天走了一万多步。", "准备洗澡睡觉了。",
]
REPLIES = ["嗯嗯，知道啦。", "好呀，早点休息。", "听起来还不错。", "辛苦啦。", "哈哈，好的。"]


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


def cn(day):
    return f"{day.month}月{day.day}日"


def story(i, k, when):
    """when(j) is the datetime of source j in this group."""
    name, friend, third, org, project, obj, doc, place, venue, city = PROFILES[i]
    pid = project + "活动"
    obj2, doc2 = OTHER_OBJECT[i], OTHER_DOC[i]
    n = i + 1
    if k == 1:
        return ([src(f"我喝咖啡只要{MILK[i]}，不加糖。"),
                 src(f"不过晚上九点以后我不喝咖啡，那时候给我推荐饮品就换成{TEA[i]}。")],
                "下午和晚上十点分别该给我推荐什么饮品？各有什么要求？",
                [f"下午咖啡要{MILK[i]}且不加糖", f"晚上九点后不喝咖啡，换成{TEA[i]}"],
                ["晚上十点推荐咖啡", "咖啡加糖"],
                f"{friend}喝咖啡喜欢加双份糖和全脂奶。")
    if k == 2:
        long = 60 + 5 * i
        return ([src(f"{project}物料尺寸\n物品\t长\t宽\t单位\n{obj}收纳箱\t{long}\t40\t厘米\n"
                     f"备用箱\t{2 + i}\t1.5\t尺", "file")],
                f"{obj}收纳箱长宽各是多少、单位是什么？备用箱也是同一个单位吗？",
                [f"收纳箱长{long}厘米", "宽40厘米", "备用箱的单位是尺，不是厘米"],
                ["备用箱单位是厘米"], None)
    if k == 3:
        return ([src(f"{friend}是我表姐，比我大三岁。"),
                 src(f"{friend}的同事{third}下周来{org}帮忙，我和{third}还不认识。")],
                f"{third}和我是什么关系？{friend}和我又是什么关系？",
                [f"{friend}是用户的表姐", f"{third}是{friend}的同事", f"用户和{third}还不认识"],
                [f"{third}是用户的同事", f"{third}是用户的亲戚"], None)
    if k == 4:
        return ([src(f"我不吃{AVOID[i]}，聚餐点菜帮我避开。"),
                 src(f"补充一下，不吃{AVOID[i]}不包括用它熬的汤底，汤底我可以喝，只是别放碎叶子。",
                     "voice")],
                f"帮我点菜时{AVOID[i]}怎么处理？用{AVOID[i]}熬的汤底可以吗？",
                [f"菜里避开{AVOID[i]}", f"{AVOID[i]}熬的汤底可以"],
                ["汤底也不行"], None)
    if k == 5:
        old = when(0) + timedelta(days=10)
        new = old + timedelta(days=7)
        return ([src(f"{doc}原定{iso(old)}前交给{org}。"),
                 src(f"{friend}发来通知：{doc}统一顺延一周，新的截止日期是{iso(new)}，"
                     "原日期作废。", "forward")],
                f"{doc}现在的截止日期是哪天？原来那个日期还有效吗？",
                [iso(new), f"原定{iso(old)}已顺延作废"], [f"仍按{iso(old)}截止"],
                f"{doc2}的截止日期没变，还是{iso(old)}。")
    if k == 6:
        return ([src(f"{obj}放在{place}的储物柜里。"),
                 src(f"{obj}挪到{venue}了。"),
                 src(f"{obj}又挪了一次，现在在{venue}二层的铁皮柜，之后就固定放这。")],
                f"{obj}现在放在哪？之前放过哪些地方？按先后说。",
                [f"现在在{venue}二层铁皮柜", f"最早在{place}储物柜", f"中间放在{venue}（未注明楼层）"],
                [f"现在还在{place}"],
                f"{obj2}一直放在{place}，没动过。")
    if k == 7:
        return ([src(f"这周末{pid}有三项：上午导览、下午手作工作坊、晚上露天放映。"),
                 src("下午的手作工作坊取消了，另外两项照常。")],
                f"这周末{pid}还剩哪些安排？哪一项取消了？",
                ["上午导览照常", "晚上露天放映照常", "下午手作工作坊取消"],
                ["全部取消", "工作坊照常举行"], None)
    if k == 8:
        mine, hers = COLORS[i][1], COLORS[i][0]
        return ([src(f"{friend}：我最喜欢{hers}，帮我做名牌就用这个颜色。", "forward"),
                 src(f"我自己其实不喜欢{hers}，我的名牌用{mine}。")],
                f"给我和{friend}做名牌，各用什么颜色？",
                [f"{friend}用{hers}", f"用户用{mine}"], [f"用户喜欢{hers}"], None)
    if k == 9:
        call = when(0) + timedelta(days=2)
        return ([src(f"你能在{cn(call)}上午提醒我给{friend}回个电话吗？", "assistant",
                     reply=f"好的，我会在{cn(call)}上午提醒你给{friend}回电话。"),
                 src(f"我没跟{friend}约好哪天回，只是自己想记得回。")],
                f"给{friend}回电话这件事，谁答应了什么？我有没有跟{friend}约定具体日期？",
                [f"助手答应在{cn(call)}上午提醒", f"用户没有跟{friend}约定具体日期"],
                [f"用户答应{friend}{cn(call)}回电"], None)
    if k == 10:
        return ([src(f"{pid}集合时间是早上7点半，在{place}。"),
                 src("引用上一条“集合时间是早上7点半”：这里写错了，应该是8点15，地点不变。",
                     "quote")],
                f"{pid}几点在哪集合？之前说的7点半为什么不用？",
                ["8点15", f"在{place}集合", "7点半是写错后被更正"], ["7点半集合"], None)
    if k == 11:
        said = when(0)
        monday = said - timedelta(days=said.weekday())
        target = monday + timedelta(days=8)
        mode = "relative_voice" if i % 2 == 0 else "text"
        return ([src(f"下周二晚上七点我要去{venue}上陶艺课，按今天说的算。", mode)],
                f"我说的那次去{venue}上陶艺课，换成公历是哪天几点？",
                [iso(target), "19:00"], ["按提问当天重新计算下周二"], None)
    if k == 12:
        out = when(0).replace(hour=10, minute=0)
        back = out + timedelta(days=3 + i % 3, hours=6)
        days = (back.date() - out.date()).days + 1
        return ([src(f"{obj}借用记录\n借出\t{iso(out)} 10:00\n归还\t{iso(back)} 16:00\n"
                     "状态\t已归还", "file")],
                f"{obj}是哪天借出、哪天归还的？按日历日含首尾一共几天？现在还回来了吗？",
                [f"{iso(out)}借出", f"{iso(back)}归还", f"共{days}个日历日", "已归还"],
                ["尚未归还"], None)
    if k == 13:
        return ([src(f"今天把{obj}送去清洗了。"), src(f"{obj}洗好取回来了。"),
                 src(f"今天给{obj}贴了新标签。")],
                f"{obj}送洗、取回、贴新标签分别是哪天？按先后排一下。",
                [f"{iso(when(0))}送洗", f"{iso(when(1))}取回", f"{iso(when(2))}贴新标签"],
                ["顺序颠倒"], f"今天把{obj2}也拿去修了。")
    if k == 14:
        mode = "voice" if i % 2 == 0 else "text"
        return ([src(f"如果周六下雨，{pid}就改到{venue}室内。"),
                 src(f"周六天晴，一滴雨都没下，{pid}按原计划在{place}户外办完了。", mode)],
                f"{pid}周六最后在哪办的？改到室内的条件触发了吗？",
                [f"在{place}户外办", "没下雨，改室内的条件没有触发"], [f"改到{venue}室内"], None)
    if k == 15:
        mode = "voice" if i % 2 else "text"
        return ([src(f"我计划这周把{doc}录进系统。"),
                 src(f"{doc}已经全部录完，系统里能查到了；纸质版还没打印。", mode)],
                f"{doc}录入现在是计划还是已完成？纸质版呢？",
                ["已经录入完成", "纸质版尚未打印"], ["录入还只是计划", "纸质版已打印"], None)
    if k == 16:
        return ([src(f"假如我明年搬去{city}，你觉得我还能参加{org}吗？只是随便假设，我没打算搬。")],
                f"我是不是要搬去{city}了？",
                ["只是假设", "没有搬家计划"], [f"用户要搬去{city}"], None)
    if k == 17:
        return ([src("我决定辞职去当灯塔看守员了——开玩笑的，下周一照常上班。")],
                "我真要辞职去当灯塔看守员吗？下周一上不上班？",
                ["那是玩笑", "下周一照常上班"], ["用户要辞职"], None)
    if k == 18:
        counts = [2 + i % 3, 1 + i % 2, 3 + i % 2]
        return ([src(f"{project}贴纸库存照片", "image", visual={"type": "colors", "title": f"{project}贴纸库存",
                                          "colors": ["红", "蓝", "黄"], "counts": counts})],
                f"{project}贴纸库存照片里红、蓝、黄色贴纸各有几张？",
                [f"红色{counts[0]}张", f"蓝色{counts[1]}张", f"黄色{counts[2]}张"],
                ["数量与图不符"], None)
    if k == 19:
        actual = 4 + i % 3
        return ([src(f"{org}{obj}清点图", "image", visual={"type": "layout", "title": f"{org}{obj}清点",
                                          "labels": [obj, "电源线", "说明书"],
                                          "counts": [2, 1, 1]}),
                 src(f"那张清点图拍早了，以我这句为准：{obj}实际有{actual}台，不是图上的数。")],
                f"{obj}现在一共几台？图上显示几台？以哪个为准？",
                [f"实际{actual}台", "图上显示2台", "以用户文字更正为准"], ["以图片为准只有2台"],
                None)
    if k == 20:
        row = 3 + i % 4
        return ([src(f"{doc}的取件码是{' '.join(CODES[i])}，柜子在{place}第{row}排。", "voice")],
                f"{doc}的取件码是多少？柜子在哪、第几排？",
                [f"取件码{CODES[i]}", f"{place}第{row}排"], ["编造其他取件码"],
                f"{doc2}不用取件码，直接找前台拿。")
    if k == 21:
        a, b = third, friend
        return ([src(f"我叫{name}，值班表上按我的名字找。"),
                 src(f"{org}值班表\n日期\t早班\t晚班\n周一\t{a}\t{b}\n周二\t{name}\t{a}\n"
                     f"周三\t{b}\t{name}", "file")],
                "值班表里我排了哪几班？周一晚班是谁？",
                ["用户排周二早班", "用户排周三晚班", f"周一晚班是{b}"], ["用户周一有班"], None)
    if k == 22:
        return ([src(f"{pid}的场地费我还没问，{friend}说回头报给我。")],
                f"{pid}的场地费是多少？谁负责报价？",
                ["场地费金额目前未知", f"{friend}负责回头报"], ["编造具体金额"], None)
    if k == 23:
        return ([src(f"我在申请调岗这事先别跟任何人说；只有{friend}问起，可以告诉她我在考虑。")],
                f"如果{third}问我最近工作有没有变动，你怎么回？{friend}问呢？",
                [f"对{third}不透露调岗", f"{friend}问起可以说用户在考虑调岗"],
                [f"向{third}透露调岗"], None)
    if k == 24:
        start = 13 + i % 4
        return ([src(f"{obj}的备用钥匙放在{friend}那儿。"),
                 src(f"{org}值班时间\n人\t时间\t地点\n{friend}\t周{WEEK[i % 5]} {start}:00-{start + 2}:00"
                     f"\t{place}\n{third}\t周{WEEK[(i + 2) % 5]} 09:00-11:00\t{venue}", "file"),
                 src(f"{friend}只有值班时间才能把钥匙拿出来。")],
                f"我想拿{obj}的备用钥匙，该找谁、什么时间、去哪？",
                [friend, f"周{WEEK[i % 5]}", f"{start}:00-{start + 2}:00", place],
                [f"找{third}"], None)
    raise KeyError(k)


def draw_image(path, visual):
    image = Image.new("RGB", (1050, 720), "#f7f6f2")
    d = ImageDraw.Draw(image)
    big, normal, small = (ImageFont.truetype(FONT, size) for size in (31, 25, 19))
    d.text((40, 25), visual["title"], fill="#2b2b2b", font=big)
    if visual["type"] == "colors":
        fills = {"红": "#d64541", "蓝": "#2f6db5", "黄": "#e8b923"}
        y = 160
        for color, count in zip(visual["colors"], visual["counts"], strict=True):
            for j in range(count):
                x = 110 + j * 150
                d.rounded_rectangle((x, y, x + 110, y + 110), radius=18, fill=fills[color],
                                    outline="#333333", width=3)
            y += 170
        d.text((40, 670), "每个圆角方块是一张贴纸。", fill="#666666", font=small)
    else:
        d.line((45, 130, 1000, 130), fill="#555555", width=3)
        d.line((525, 130, 525, 650), fill="#cccccc", width=3)
        d.line((45, 400, 1000, 400), fill="#cccccc", width=3)
        centers = [(250, 250), (740, 250), (525, 510)]
        for i, (label, count, center) in enumerate(zip(visual["labels"], visual["counts"], centers,
                                                       strict=True)):
            for j in range(count):
                x, y = center[0] - (count - 1) * 47 + j * 94, center[1]
                shape = (x - 33, y - 30, x + 33, y + 30)
                if i == 0:
                    d.rectangle(shape, fill="#6b8e6b", outline="#2f4f2f", width=3)
                elif i == 1:
                    d.ellipse(shape, fill="#c9a96e", outline="#6e5a35", width=3)
                else:
                    d.rectangle((x - 25, y - 35, x + 25, y + 35), fill="#ffffff",
                                outline="#444444", width=3)
            d.text((center[0] - len(label) * 12, center[1] + 60), label, fill="#2b2b2b",
                   font=normal)
        d.text((40, 670), "数量以图中实际图形个数为准。", fill="#666666", font=small)
    image.save(path)


def main():
    BANK.mkdir(exist_ok=False)
    for directory in ("assets", "inputs", "review-only"):
        (SUITE / directory).mkdir(parents=True)
    questions, criteria, audio, provenance = [], [], [], []
    for index in range(len(PROFILES)):
        persona = f"M{index + 1:02}"
        slots_used, groups = {}, []
        for k in range(1, 25):
            base = 2 * (5 + 5 * k)
            plan = [base, base + 3, base + 5, base + 7]
            preview = story(index, k, lambda j: date(plan[j]))
            count = len(preview[0])
            slots = plan[:count]
            sources, question, required, forbidden, distractor = preview
            ids, modes = [], []
            for j, (slot, source) in enumerate(zip(slots, sources, strict=True)):
                sid = f"{persona}-Q{k:02}-S{j + 1}"
                mode = source["mode"]
                asset = None
                if mode in ("image", "file", "voice", "relative_voice"):
                    suffix = {"image": "png", "file": "txt"}.get(mode, "wav")
                    asset = f"assets/{sid}.{suffix}"
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
                slots_used[slot] = {"id": f"{persona}-Q{k:02}-X1", "now": date(slot).isoformat(),
                                    "modality": "text", "text": distractor, "asset": None,
                                    "caption": None, "assistant_reply": "好，记下了。"}
            anchor = date(slots[-1])
            category, family = CATEGORIES[k - 1]
            groups.append({"k": k, "anchor": anchor, "question": question, "required": required,
                           "forbidden": forbidden, "source_ids": ids, "category": category,
                           "family": family, "input_modalities": sorted(set(modes))})
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
                qid = f"{persona}-Q{group['k']:02}/d{delay:02}"
                questions.append({
                    "id": qid, "persona": persona, "group_id": f"{persona}-Q{group['k']:02}",
                    "now": when.isoformat(), "cutoff_turn": bisect.bisect_right(times, when),
                    "question": group["question"], "source_ids": group["source_ids"],
                    "category": group["category"], "category_id": f"Q{group['k']:02}",
                    "family": group["family"], "delay_days": delay, "kind": "semantic_memory",
                    "input_modalities": group["input_modalities"]})
                criteria.append({"id": qid, "required": group["required"],
                                 "forbidden": group["forbidden"],
                                 "source_ids": group["source_ids"]})
        rows(SUITE / "inputs" / f"{persona}.jsonl", history)
    rows(SUITE / "questions.jsonl", questions)
    rows(SUITE / "review-only/criteria.jsonl", criteria)
    rows(SUITE / "review-only/source-authoring-provenance.jsonl", provenance)
    rows(ROOT / "audio-to-synthesize.jsonl", audio)
    write_json(ROOT / "bank-authoring-status.json", {
        "status": "AUTHORED_PENDING_WAV_ASR_VALIDATION_AND_FREEZE",
        "authored_at": datetime.now(timezone.utc).isoformat(), "semantic": len(questions),
        "fact_groups": len(criteria) // 4, "source_records": len(provenance),
        "audio_assets": len(audio),
        "question_modality_memberships": dict(Counter(
            m for q in questions for m in q["input_modalities"])),
        "authoring_script_sha256": sha(Path(__file__)), "old_corpus_imported": False})
    print(json.dumps({"semantic": len(questions), "groups": len(criteria) // 4,
                      "audio_pending": len(audio)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
